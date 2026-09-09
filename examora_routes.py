# -*- coding: utf-8 -*-
"""
Examora AI Extended Routes
Registers endpoints for:
1. Public student online exam API (for Firebase Hosting at https://yt-c-c.web.app/#)
2. Retake / Individual exam creation and official result replacement
3. Teacher full administrative deletion and attempt reset
4. Staged online exam publishing lifecycle (Active -> Closed -> Synced -> Purged)
5. Teachers' community forum
6. Suggestions and complaints system with in-app notifications
"""
import json, secrets
from datetime import datetime, timedelta
try:
    from flask import request, session, redirect, url_for, flash, jsonify, render_template
except ImportError:
    from mini_flask import request, session, redirect, url_for, flash, jsonify, render_template

def register_examora_routes(app, db, srv):
    if getattr(app, '_examora_routes_registered', False):
        return
    app._examora_routes_registered = True

    # -------------------------------------------------------------
    # 1. PUBLIC ONLINE EXAM API (For https://yt-c-c.web.app/#)
    # -------------------------------------------------------------
    @app.route('/api/public/exam/start', methods=['POST'])
    def api_public_exam_start():
        data = request.json or request.form
        national_id = (data.get('national_id') or data.get('student_id') or '').strip()
        exam_code = (data.get('exam_code') or data.get('code') or data.get('token') or '').strip()

        if not national_id or not exam_code:
            return jsonify({'ok': False, 'error': 'يرجى إدخال الرقم الوطني ورمز دخول الامتحان.'}), 400

        # Find student by national_id or username
        student = db.q("""
            SELECT * FROM students 
            WHERE (national_id=? OR LOWER(username)=?) AND active=1
        """, (national_id, national_id.lower()), one=True)
        if not student:
            return jsonify({'ok': False, 'error': 'الرقم الوطني للطالب غير مسجل أو الحساب غير مفعّل.'}), 404

        # Find exam by exam_code or published_exams token or ID
        exam = None
        # Check published exams first
        pub = db.q("SELECT * FROM published_exams WHERE publish_token=? AND status='ACTIVE'", (exam_code,), one=True)
        if pub:
            exam = db.q("SELECT * FROM exams WHERE id=?", (pub['local_exam_id'],), one=True)
        else:
            exam = db.q("SELECT * FROM exams WHERE (exam_code=? OR id=?) AND is_archived=0", (exam_code, exam_code), one=True)

        if not exam:
            return jsonify({'ok': False, 'error': 'رمز الامتحان غير صحيح أو أن الامتحان غير متاح حالياً.'}), 404

        # Verify student eligibility and subject enrollment
        is_allowed, msg, exam_row, student_row = srv.validate_student_exam_access(exam['id'], student['id'])
        if not is_allowed:
            return jsonify({'ok': False, 'error': msg}), 403

        # Start or resume attempt
        ip_addr = request.remote_addr if hasattr(request, 'remote_addr') else ''
        att_res = srv.get_or_create_active_attempt(exam['id'], student['id'], ip_address=ip_addr)

        if 'error' in att_res and att_res['error'] == 'ALREADY_SUBMITTED':
            return jsonify({
                'ok': False,
                'error': 'لقد قمت بتقديم هذا الامتحان مسبقاً وتم تسليم إجاباتك. لا يُسمح بإعادة التقديم إلا بإذن مباشر من معلم المادة.'
            }), 403

        # Prepare questions payload (STRICTLY NO correct answers sent to browser)
        questions = srv.get_student_exam_payload(att_res['attempt_id'])

        return jsonify({
            'ok': True,
            'attempt_id': att_res['attempt_id'],
            'remaining_seconds': att_res['remaining_seconds'],
            'is_resumed': att_res['is_resumed'],
            'answers': att_res['answers'],
            'exam': {
                'id': exam['id'],
                'title': exam['title'],
                'subject': exam['subject'],
                'duration': exam['duration'],
                'total_marks': exam['total_marks']
            },
            'student': {
                'id': student['id'],
                'full_name': student['full_name'],
                'national_id': student['national_id']
            },
            'questions': questions
        })

    @app.route('/api/public/exam/autosave', methods=['POST'])
    def api_public_exam_autosave():
        data = request.json or request.form
        attempt_id = data.get('attempt_id')
        question_id = data.get('question_id')
        answer = (data.get('answer') or '').strip()

        if not attempt_id or not question_id:
            return jsonify({'ok': False, 'error': 'بيانات غير مكتملة'}), 400

        att = db.q("SELECT * FROM attempts WHERE id=?", (attempt_id,), one=True)
        if not att or att['status'] != 'ACTIVE':
            return jsonify({'ok': False, 'error': 'المحاولة غير نشطة أو انتهت مدتها'}), 400

        snap = db.q("SELECT * FROM attempt_snapshots WHERE attempt_id=? AND question_id=?", (attempt_id, question_id), one=True)
        snap_id = snap['id'] if snap else None
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Upsert answer
        existing = db.q("SELECT id FROM answers WHERE attempt_id=? AND question_id=?", (attempt_id, question_id), one=True)
        if existing:
            db.x("UPDATE answers SET answer=?, answered_at=? WHERE id=?", (answer, now_str, existing['id']))
        else:
            srv.insert('answers', {
                'attempt_id': attempt_id,
                'snapshot_id': snap_id,
                'question_id': question_id,
                'answer': answer,
                'correct': snap['correct_option'] if snap else '',
                'is_correct': 1 if (snap and snap['correct_option'] == answer) else 0,
                'mark': snap['mark'] if snap else 1.0,
                'answered_at': now_str
            })

        db.x("UPDATE attempts SET last_activity_at=? WHERE id=?", (now_str, attempt_id))
        return jsonify({'ok': True})

    @app.route('/api/public/exam/submit', methods=['POST'])
    def api_public_exam_submit():
        data = request.json or request.form
        attempt_id = data.get('attempt_id')
        answers = data.get('answers') or {}

        if not attempt_id:
            return jsonify({'ok': False, 'error': 'معرف المحاولة مطلوب'}), 400

        att = db.q("SELECT * FROM attempts WHERE id=?", (attempt_id,), one=True)
        if not att:
            return jsonify({'ok': False, 'error': 'المحاولة غير موجودة'}), 404

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Save final answers
        snapshots = db.q("SELECT * FROM attempt_snapshots WHERE attempt_id=?", (attempt_id,))
        total_score = 0.0
        total_marks = 0.0

        for s in snapshots:
            qid = s['question_id']
            q_mark = float(s['mark']) if s['mark'] else 1.0
            total_marks += q_mark
            selected = str(answers.get(str(qid)) or answers.get(qid) or '').strip()

            is_correct = 1 if (selected and selected == s['correct_option']) else 0
            awarded = q_mark if is_correct else 0.0
            total_score += awarded

            existing = db.q("SELECT id FROM answers WHERE attempt_id=? AND question_id=?", (attempt_id, qid), one=True)
            if existing:
                db.x("UPDATE answers SET answer=?, is_correct=?, mark=?, answered_at=? WHERE id=?",
                     (selected, is_correct, awarded, now_str, existing['id']))
            else:
                srv.insert('answers', {
                    'attempt_id': attempt_id,
                    'snapshot_id': s['id'],
                    'question_id': qid,
                    'answer': selected,
                    'correct': s['correct_option'],
                    'is_correct': is_correct,
                    'mark': awarded,
                    'answered_at': now_str
                })

        percentage = (total_score / total_marks * 100) if total_marks > 0 else 0.0

        # Determine Tier & encouraging message from settings
        tier = 'مقبول'
        setting_key = 'msg_acceptable'
        if percentage >= 90:
            tier = 'ممتاز'
            setting_key = 'msg_excellent'
        elif percentage >= 80:
            tier = 'جيد جداً'
            setting_key = 'msg_very_good'
        elif percentage >= 65:
            tier = 'جيد'
            setting_key = 'msg_good'

        feedback_msg = db.setting(setting_key) or f"أحسنت صنعاً! تقديرك في هذا الاختبار هو: {tier}."

        # Finalize Attempt
        db.x("""
            UPDATE attempts 
            SET status='SUBMITTED', score=?, total=?, percentage=?, finished_at=?, submitted_at=?, last_activity_at=?
            WHERE id=?
        """, (total_score, total_marks, percentage, now_str, now_str, now_str, attempt_id))

        db.audit(att['student_name'], 'SUBMIT_ONLINE_EXAM', 'attempts', attempt_id,
                 after_state=f"Score: {total_score}/{total_marks} ({percentage:.1f}%)")

        return jsonify({
            'ok': True,
            'score': total_score,
            'total': total_marks,
            'percentage': percentage,
            'tier': tier,
            'feedback_message': feedback_msg
        })

    # -------------------------------------------------------------
    # 2. RETAKE & INDIVIDUAL EXAMS
    # -------------------------------------------------------------
    @app.route('/exams/retake/create', methods=['POST'])
    def exams_retake_create():
        if not session.get('admin_logged_in'):
            flash('يرجى تسجيل الدخول للوصول إلى هذا الإجراء.', 'error')
            return redirect(url_for('login'))

        orig_exam_id = request.form.get('original_exam_id')
        student_id = request.form.get('student_id')
        title = (request.form.get('title') or '').strip()
        duration = int(request.form.get('duration') or 30)
        reason = (request.form.get('reason') or '').strip()
        q_ids = request.form.getlist('question_ids')

        if not orig_exam_id or not student_id or not q_ids:
            flash('يرجى اختيار الطالب والامتحان والأسئلة المطلوبة للامتحان التعويضي.', 'error')
            return redirect(url_for('results_dashboard'))

        try:
            actor = session.get('user_email') or session.get('admin_name') or 'TEACHER'
            res = srv.create_retake_exam(
                original_exam_id=int(orig_exam_id),
                student_id=int(student_id),
                title=title,
                duration=duration,
                question_ids=q_ids,
                reason=reason,
                actor=actor
            )
            flash(f"تم إنشاء الامتحان التعويضي بنجاح للطالب ({res['student_name']}) برمز دخول: {res['exam_code']}", 'success')
            return redirect(url_for('exams_list'))
        except Exception as e:
            flash(f"تعذر إنشاء الامتحان التعويضي: {e}", 'error')
            return redirect(url_for('results_dashboard'))

    @app.route('/results/replace-official', methods=['POST'])
    def results_replace_official():
        if not session.get('admin_logged_in'):
            flash('يرجى تسجيل الدخول للوصول إلى هذا الإجراء.', 'error')
            return redirect(url_for('login'))

        orig_att_id = request.form.get('original_attempt_id')
        retake_att_id = request.form.get('retake_attempt_id')
        reason = (request.form.get('reason') or '').strip()

        if not orig_att_id or not retake_att_id:
            flash('بيانات المحاولات غير مكتملة.', 'error')
            return redirect(url_for('results_dashboard'))

        try:
            actor = session.get('user_email') or session.get('admin_name') or 'TEACHER'
            srv.replace_official_result(int(orig_att_id), int(retake_att_id), reason=reason, actor=actor)
            flash('تم اعتماد علامة المحاولة التعويضية رسمياً، وتوثيق المحاولة السابقة في السجل التاريخي بنجاح.', 'success')
        except Exception as e:
            flash(f"تعذر اعتماد النتيجة: {e}", 'error')

        return redirect(url_for('results_dashboard'))

    # -------------------------------------------------------------
    # 3. ATTEMPTS & ANSWERS MANAGEMENT (Teacher Full Authority)
    # -------------------------------------------------------------
    @app.route('/results/attempt/<int:id>/delete', methods=['POST'])
    def results_delete_attempt(id):
        if not session.get('admin_logged_in'):
            flash('يرجى تسجيل الدخول للوصول إلى هذا الإجراء.', 'error')
            return redirect(url_for('login'))

        reason = (request.form.get('reason') or '').strip()
        actor = session.get('user_email') or session.get('admin_name') or 'TEACHER'

        ok = srv.delete_attempt(id, reason=reason, actor=actor)
        if ok:
            flash(f'تم حذف المحاولة رقم #{id} وإجاباتها ولقطتها نهائياً من النظام.', 'success')
        else:
            flash('المحاولة غير موجودة أو تم حذفها مسبقاً.', 'error')

        return redirect(url_for('results_dashboard'))

    @app.route('/results/attempt/<int:id>/reset', methods=['POST'])
    def results_reset_attempt(id):
        if not session.get('admin_logged_in'):
            flash('يرجى تسجيل الدخول للوصول إلى هذا الإجراء.', 'error')
            return redirect(url_for('login'))

        reason = (request.form.get('reason') or '').strip()
        actor = session.get('user_email') or session.get('admin_name') or 'TEACHER'

        ok = srv.reset_attempt(id, reason=reason, actor=actor)
        if ok:
            flash(f'تم إعادة تعيين المحاولة رقم #{id} بنجاح، ويمكن للطالب الآن إعادة تقديمها.', 'success')
        else:
            flash('تعذر إعادة تعيين المحاولة.', 'error')

        return redirect(url_for('results_dashboard'))

    # -------------------------------------------------------------
    # 4. ONLINE EXAM STAGING & PUBLISHING LIFECYCLE
    # -------------------------------------------------------------
    @app.route('/exams/<int:id>/publish-online', methods=['POST'])
    def exams_publish_online(id):
        if not session.get('admin_logged_in'):
            flash('يرجى تسجيل الدخول للوصول إلى هذا الإجراء.', 'error')
            return redirect(url_for('login'))

        try:
            actor = session.get('user_email') or session.get('admin_name') or 'TEACHER'
            scheduled_start_at = request.form.get('scheduled_start_at')
            scheduled_end_at = request.form.get('scheduled_end_at')
            res = srv.publish_exam_online(id, actor=actor, scheduled_start_at=scheduled_start_at, scheduled_end_at=scheduled_end_at)
            flash(f"تم تجهيز ونشر الامتحان أونلاين بنجاح! الرابط المباشر: {res['web_link']}", 'success')
        except Exception as e:
            flash(f"تعذر نشر الامتحان: {e}", 'error')

        return redirect(url_for('exam_manage', id=id))

    @app.route('/exams/published/<token>/close', methods=['POST'])
    def exams_close_published(token):
        if not session.get('admin_logged_in'):
            flash('يرجى تسجيل الدخول للوصول إلى هذا الإجراء.', 'error')
            return redirect(url_for('login'))

        srv.close_published_exam(token, actor=session.get('user_email', 'TEACHER'))
        flash('تم إغلاق الامتحان المنشور وإيقاف قبول أي محاولات جديدة.', 'info')
        return redirect(url_for('exams_list'))

    @app.route('/exams/published/<token>/sync', methods=['POST'])
    def exams_sync_published(token):
        if not session.get('admin_logged_in'):
            flash('يرجى تسجيل الدخول للوصول إلى هذا الإجراء.', 'error')
            return redirect(url_for('login'))

        pub = db.q("SELECT local_exam_id FROM published_exams WHERE publish_token=?", (token,), one=True)
        try:
            synced = srv.sync_published_attempts(token, actor=session.get('user_email', 'TEACHER'))
            flash(f'تمت مزامنة ({synced}) نتيجة من السيرفر السحابي وتحديث بيانات الامتحان محلياً بنجاح! 🔄', 'success')
        except Exception as e:
            flash(f'تعذر إتمام المزامنة: {e}', 'error')

        if pub and pub.get('local_exam_id'):
            return redirect(url_for('exam_manage', id=pub['local_exam_id']))
        return redirect(url_for('exams_list'))

    @app.route('/api/sync/auto', methods=['GET', 'POST'])
    def api_auto_sync_endpoint():
        if not session.get('admin_logged_in'):
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
        res = srv.auto_sync_all_active_exams(actor=session.get('user_email', 'AUTO_SYNC'))
        return jsonify(res)

    @app.route('/exams/<int:id>/sync-online', methods=['POST'])
    def exams_sync_online_by_id(id):
        if not session.get('admin_logged_in'):
            flash('يرجى تسجيل الدخول للوصول إلى هذا الإجراء.', 'error')
            return redirect(url_for('login'))

        pub = db.q("SELECT publish_token FROM published_exams WHERE local_exam_id=? ORDER BY id DESC LIMIT 1", (id,), one=True)
        if not pub or not pub.get('publish_token'):
            flash('هذا الامتحان لم يتم نشره أونلاين بعد، لا توجد نتائج للمزامنة.', 'warning')
            return redirect(url_for('exam_manage', id=id))

        try:
            synced = srv.sync_published_attempts(pub['publish_token'], actor=session.get('user_email', 'TEACHER'))
            flash(f'تمت مزامنة ({synced}) نتيجة من السيرفر السحابي وتحديث بيانات الامتحان محلياً بنجاح! 🔄', 'success')
        except Exception as e:
            flash(f'تعذر إتمام المزامنة: {e}', 'error')

        return redirect(url_for('exam_manage', id=id))

    @app.route('/exams/published/<token>/purge', methods=['POST'])
    def exams_purge_published(token):
        if not session.get('admin_logged_in'):
            flash('يرجى تسجيل الدخول للوصول إلى هذا الإجراء.', 'error')
            return redirect(url_for('login'))

        try:
            srv.purge_published_exam(token, actor=session.get('user_email', 'TEACHER'))
            flash('تم حذف النسخة المنشورة أونلاين مع الاحتفاظ بكافة السجلات والنتائج محلياً.', 'success')
        except Exception as e:
            flash(f"تعذر الحذف: {e}", 'error')

        return redirect(url_for('exams_list'))

    # -------------------------------------------------------------
    # 5. TEACHERS' COMMUNITY FORUM
    # -------------------------------------------------------------
    @app.route('/forum', methods=['GET'], endpoint='forum_home')
    def forum_home():
        if not session.get('admin_logged_in'):
            flash('يرجى تسجيل الدخول للوصول إلى منتدى الأساتذة.', 'error')
            return redirect(url_for('login'))

        category = request.args.get('category')
        q = (request.args.get('q') or '').strip()

        sql = "SELECT t.*, (SELECT COUNT(*) FROM forum_replies WHERE topic_id=t.id) as replies_count FROM forum_topics t WHERE 1=1"
        params = []
        if category:
            sql += " AND category=?"
            params.append(category)
        if q:
            sql += " AND (title LIKE ? OR content LIKE ?)"
            params.extend([f'%{q}%', f'%{q}%'])

        sql += " ORDER BY is_pinned DESC, id DESC"
        topics = db.q(sql, params)
        total_count = db.q("SELECT COUNT(*) as n FROM forum_topics", one=True)['n']

        return render_template('forum.html',
                               title='منتدى الأساتذة الموحد',
                               subtitle='مساحة تشاركية لتبادل الخبرات والأسئلة والأفكار التعليمية',
                               active='forum',
                               topics=topics,
                               total_topics=total_count,
                               selected_category=category,
                               search_query=q)

    @app.route('/forum/topic/create', methods=['POST'], endpoint='forum_create_topic')
    def forum_create_topic():
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))

        title = (request.form.get('title') or '').strip()
        content = (request.form.get('content') or '').strip()
        category = (request.form.get('category') or 'عام').strip()

        if not title or not content:
            flash('يرجى كتابة عنوان ومحتوى الموضوع.', 'error')
            return redirect(url_for('forum_home'))

        author_name = session.get('admin_name') or 'معلم'
        author_email = session.get('user_email') or 'teacher@school.jo'
        author_id = session.get('teacher_id') or 1

        tid = srv.create_forum_topic(author_id, author_name, author_email, title, content, category)
        flash('تم نشر الموضوع بنجاح في منتدى الأساتذة.', 'success')
        return redirect(url_for('forum_topic_view', id=tid))

    @app.route('/forum/topic/<int:id>', methods=['GET'], endpoint='forum_topic_view')
    def forum_topic_view(id):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))

        topic = db.q("SELECT * FROM forum_topics WHERE id=?", (id,), one=True)
        if not topic:
            flash('الموضوع غير موجود أو تم حذفه.', 'error')
            return redirect(url_for('forum_home'))

        # Increment views count
        db.x("UPDATE forum_topics SET views_count = views_count + 1 WHERE id=?", (id,))

        replies = db.q("SELECT * FROM forum_replies WHERE topic_id=? ORDER BY id ASC", (id,))
        return render_template('forum_topic.html',
                               title=topic['title'],
                               subtitle=f"منتدى الأساتذة • قسم {topic['category']}",
                               active='forum',
                               topic=topic,
                               replies=replies)

    @app.route('/forum/topic/<int:id>/reply', methods=['POST'], endpoint='forum_add_reply')
    def forum_add_reply(id):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))

        content = (request.form.get('content') or '').strip()
        if not content:
            flash('يرجى كتابة محتوى الرد.', 'error')
            return redirect(url_for('forum_topic_view', id=id))

        author_name = session.get('admin_name') or 'معلم'
        author_email = session.get('user_email') or 'teacher@school.jo'
        author_id = session.get('teacher_id') or 1

        srv.add_forum_reply(id, author_id, author_name, author_email, content)
        flash('تمت إضافة ردك بنجاح.', 'success')
        return redirect(url_for('forum_topic_view', id=id))

    @app.route('/forum/topic/<int:id>/like', methods=['POST'], endpoint='forum_toggle_like')
    def forum_toggle_like(id):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))

        user_email = session.get('user_email') or 'user@school.jo'
        srv.toggle_forum_like(id, user_email)
        return redirect(url_for('forum_topic_view', id=id))

    @app.route('/forum/topic/<int:id>/delete', methods=['POST'], endpoint='forum_delete_topic')
    def forum_delete_topic(id):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))

        topic = db.q("SELECT * FROM forum_topics WHERE id=?", (id,), one=True)
        if topic:
            is_admin = session.get('is_super_admin')
            if is_admin or session.get('user_email') == topic['author_email']:
                db.x("DELETE FROM forum_replies WHERE topic_id=?", (id,))
                db.x("DELETE FROM forum_likes WHERE topic_id=?", (id,))
                db.x("DELETE FROM forum_topics WHERE id=?", (id,))
                flash('تم حذف الموضوع بنجاح.', 'info')

        return redirect(url_for('forum_home'))

    # -------------------------------------------------------------
    # 6. SUGGESTIONS & COMPLAINTS
    # -------------------------------------------------------------
    @app.route('/complaints', methods=['GET'], endpoint='complaints_home')
    def complaints_home():
        if not session.get('admin_logged_in'):
            flash('يرجى تسجيل الدخول للوصول إلى هذا القسم.', 'error')
            return redirect(url_for('login'))

        user_email = session.get('user_email') or ''
        tickets = db.q("SELECT * FROM complaints_suggestions WHERE teacher_email=? ORDER BY id DESC", (user_email,))
        return render_template('complaints.html',
                               title='المقترحات والشكاوى',
                               subtitle='إرسال الملاحظات ومتابعة ردود الإدارة عليها',
                               active='complaints',
                               tickets=tickets)

    @app.route('/complaints/submit', methods=['POST'], endpoint='complaints_submit')
    def complaints_submit():
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))

        ttype = request.form.get('type') or 'اقتراح'
        title = (request.form.get('title') or '').strip()
        description = (request.form.get('description') or '').strip()
        priority = request.form.get('priority') or 'NORMAL'

        if not title or not description:
            flash('يرجى ملء جميع الحقول المطلوبة.', 'error')
            return redirect(url_for('complaints_home'))

        teacher_id = session.get('teacher_id') or 1
        teacher_name = session.get('admin_name') or 'معلم'
        teacher_email = session.get('user_email') or 'teacher@school.jo'

        ticket_num = srv.submit_ticket(teacher_id, teacher_name, teacher_email, ttype, title, description, priority)
        flash(f'تم إرسال طلبك بنجاح بالرقم المرجعي: {ticket_num}. سيتم إشعارك فور رد الإدارة.', 'success')
        return redirect(url_for('complaints_home'))

    @app.route('/admin/complaints', methods=['GET'], endpoint='admin_complaints_view')
    def admin_complaints_view():
        if not session.get('admin_logged_in') or not session.get('is_super_admin'):
            flash('هذه الشاشة مخصصة لإدارة النظام فقط.', 'error')
            return redirect(url_for('dashboard'))

        status_filter = request.args.get('status')
        sql = "SELECT * FROM complaints_suggestions WHERE 1=1"
        params = []
        if status_filter:
            sql += " AND status=?"
            params.append(status_filter)
        sql += " ORDER BY id DESC"

        tickets = db.q(sql, params)
        total_cnt = db.q("SELECT COUNT(*) as n FROM complaints_suggestions", one=True)['n']

        return render_template('admin_complaints.html',
                               title='إدارة المقترحات والشكاوى',
                               subtitle='مراجعة طلبات الأساتذة والرد عليها رسمياً',
                               active='admin_complaints',
                               tickets=tickets,
                               total_count=total_cnt,
                               selected_status=status_filter)

    @app.route('/admin/complaints/<int:id>/respond', methods=['POST'], endpoint='admin_respond_ticket')
    def admin_respond_ticket(id):
        if not session.get('admin_logged_in') or not session.get('is_super_admin'):
            return redirect(url_for('dashboard'))

        status = request.form.get('status') or 'IN_PROGRESS'
        resp_text = (request.form.get('response_text') or '').strip()

        if not resp_text:
            flash('يرجى كتابة نص الرد للإرسال إلى المعلم.', 'error')
            return redirect(url_for('admin_complaints_view'))

        admin_name = session.get('admin_name') or 'مدير النظام'
        srv.respond_to_ticket(id, status, resp_text, admin_name)
        flash('تم حفظ الرد وتحديث حالة الطلب وإرسال الإشعار للمعلم بنجاح.', 'success')
        return redirect(url_for('admin_complaints_view'))
