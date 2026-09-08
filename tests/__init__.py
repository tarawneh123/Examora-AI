# -*- coding: utf-8 -*-
import os, sys, shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / 'exam_data'
PROD_DB = DATA_DIR / 'exam_platform.db'
TEST_ISOLATED = Path('/tmp') / 'isolated_test_exam_platform.db'

if PROD_DB.exists():
    shutil.copyfile(str(PROD_DB), str(TEST_ISOLATED))

os.environ['EXAM_PLATFORM_DB'] = str(TEST_ISOLATED)
