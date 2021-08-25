import json
import sys
import time
from flask import render_template
from rq import get_current_job
from . import create_app
from .email import send_email
import os

# def get_current_job(*args):
#     return None


app = create_app()
app.app_context().push()


def _set_task_progress(progress):
    job = get_current_job()
    if job:
        job.meta['progress'] = progress
        job.save_meta()


def email_logs():
    try:
        _set_task_progress(0)
        os.system('journalctl --boot=0 > logs.log')
        app.logger.info('Export complete, compressing...')
        _set_task_progress(33)
        os.system('tar cjf logs.tar.bz2 logs.log')
        app.logger.info('Compression complete, reading data...')
        _set_task_progress(66)
        with open('logs.tar.bz2', 'rb') as f:
            logdata = f.read()
        app.logger.info('Reading complete, sending email ...')
        _set_task_progress(75)
        send_email('[Cloudlight] Log File', sender=app.config['MAIL_USERNAME'], recipients=app.config['ADMINS'],
                    text_body='Sent by click', attachments=[('logs.tar.bz2', 'application/gzip', logdata)], sync=True)
        app.logger.info('Done.')
        _set_task_progress(100)
    except:
        app.logger.error('Unhandled exception', exc_info=True)
    finally:
        try:
            os.remove('logs.log')
        except:
            pass
        try:
            os.remove('logs.tar.bz2')
        except:
            pass
        _set_task_progress(100)
