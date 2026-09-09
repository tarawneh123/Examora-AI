# -*- coding: utf-8 -*-
"""
Online Backend Server-Side Scoring Engine
Evaluates student exam submissions exclusively on the server using the private answer key.
Zero client-side trust: Any client-provided score or mark is strictly discarded.
"""

def evaluate_exam_submission(student_answers: dict, answer_key: dict) -> dict:
    """
    Evaluates student answers against the private server answer key.
    Handles both dict format {qid: {"correct": "أ", "mark": 5.0}} and simple format {qid: "أ"}.
    """
    total_score = 0.0
    total_marks = 0.0

    if not isinstance(answer_key, dict):
        answer_key = {}

    for qid_str, key_info in answer_key.items():
        if isinstance(key_info, dict):
            q_mark = float(key_info.get('mark', 1.0) or 1.0)
            correct_ans = str(key_info.get('correct', '') or '').strip()
        else:
            q_mark = 1.0
            correct_ans = str(key_info or '').strip()

        total_marks += q_mark
        
        # Handle string and integer key lookups
        std_ans = str(student_answers.get(str(qid_str)) or student_answers.get(int(qid_str) if str(qid_str).isdigit() else qid_str) or '').strip()

        if std_ans and std_ans == correct_ans:
            total_score += q_mark

    percentage = (total_score / total_marks * 100.0) if total_marks > 0 else 0.0

    # Determine Grade Tier and Encouraging Message
    if percentage >= 90:
        tier = 'ممتاز'
        msg = 'ما شاء الله! أداء استثنائي ونتيجة متميزة تدعو للفخر.'
    elif percentage >= 80:
        tier = 'جيد جداً'
        msg = 'أحسنت! أداء رائع ونتيجة مشرفة جداً.'
    elif percentage >= 65:
        tier = 'جيد'
        msg = 'جهد طيب، ونتطلع لمزيد من التقدم في الاختبارات القادمة.'
    else:
        tier = 'مقبول'
        msg = 'أحسنت صنعاً! تم تسليم إجاباتك بنجاح واعتماد نتيجتك.'

    return {
        'score': round(total_score, 2),
        'total': round(total_marks, 2),
        'percentage': round(percentage, 2),
        'tier': tier,
        'feedback_message': msg
    }
