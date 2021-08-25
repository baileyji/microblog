import os
import subprocess
from datetime import datetime

import numpy as np
from flask import render_template, flash, redirect, url_for, request, g, \
    jsonify, current_app, Response, copy_current_request_context
from flask_login import current_user, login_required
from flask_babel import _, get_locale

import cloudlight.fadecandy
from cloudlight.util import get_services as cloudlight_services
from cloudlight.util import get_service as cloudlight_service
from .. import db
from .forms import EmptyForm
from ..models import User, Post, Message, Notification
from ..translate import translate
from . import bp
from ..api.errors import bad_request
import time, json, threading
import plotly
import plotly.express as px
import numpy as np
import json
from rq.job import Job
from cloudlight.fadecandy import EFFECTS
from .helpers import *


def guess_language(x):
    return 'en'


@bp.before_app_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
    g.locale = str(get_locale())
    redis = current_app.redis
    # redis = cloudlight.cloudredis.setup_redis(use_schema=False, module=False)
    g.redis = redis
    g.mode = redis.read('lamp:mode')


@bp.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store'
    return response


@bp.route('/', methods=['GET', 'POST'])
@bp.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    modes = tuple((key, e.name) for key, e in cloudlight.fadecandy.EFFECTS.items())
    if request.method == 'POST':
        mode = request.form['mode_key']
        e = EFFECTS[mode]
        f = e.form(mode_name=e.name, mode_key=e.key)
        if f.validate_on_submit():
            settings = f.data
            for k in ('csrf_token', 'mode_name', 'mode_key', 'submit'):
                settings.pop(k)
            g.redis.store(f'lamp:{mode}:settings', settings)
            if g.redis.read('lamp:mode') == mode:
                g.redis.store(f'lamp:settings', True, publish_only=True)
            else:
                g.redis.store(f'lamp:mode', mode)

            return redirect(url_for('main.lamp'))
    else:
        f = cloudlight.fadecandy.build_form(g.redis.read('lamp:mode'), g.redis)

    return render_template('index.html', title=_('Cloudlight'), modes=modes, form=f, active_mode=g.mode)


@bp.route('/rediscontrol', methods=['POST', 'GET'])
@login_required
def rediscontrol():
    """Handle read and write requests for redis keys"""
    if request.method == 'POST':
        try:
            val = float(request.form['value'])
        except ValueError:
            val = request.form['value']
        try:
            current_app.redis.store(request.form['source'].partition(':')[2], val)
            return jsonify({'success': True})
        except:
            current_app.logger.error('post error', exc_info=True)
    else:
        try:
            return jsonify({'value': current_app.redis.read(request.args.get('key'))})
        except:
            current_app.logger.error(f'get error {request.args}', exc_info=True)
    return bad_request('control failed')


# Controls need to be named with their redis key
@bp.route('/stream',  methods=['GET'])
@login_required
def stream():
    from ....config import REDIS_SCHEMA
    import cloudlight.cloudredis as clr
    event = request.args.get('event', 'update', type=str)

    # @copy_current_request_context
    def _stream():
        # for k, v in g.redis.listen(REDIS_SCHEMA['keys']):
        for k, v in clr.redis.listen(REDIS_SCHEMA['keys']):
            event = 'update'
            data = {k: v}

            # plotid = 'temp:value'
            # since = None
            # kind = 'full' if since is None else 'partial'
            # new = list(zip(*redis.range(plotid, since)))
            # data = {'id': f'redisplot:{plotid}', 'kind': kind, 'data': {'x': new[0], 'y': new[1]}}

            yield f"event:{event}\nretry:5\ndata: {json.dumps(data)}\n\n"

    return current_app.response_class(_stream(), mimetype="text/event-stream")


@bp.route('/shutdown', methods=['POST'])
@login_required
def shutdown():
    """data: shutdown|reboot """
    cmd = request.form.get('data', '')
    if cmd in ('shutdown', 'reboot'):
        subprocess.Popen(['/home/pi/.local/bin/cloud-service-control', cmd])
        flash(f'System going offline for {cmd}')
        return jsonify({'success': True})
    else:
        return bad_request('Invalid shutdown command')


@bp.route('/task', methods=['GET', 'POST'])
@login_required
def task():
    from rq.job import NoSuchJobError
    if request.method == 'POST':
        id = request.form.get('id')
        if id != 'email-logs':
            return bad_request('Unknown task')
        try:
            job = Job.fetch(id, connection=g.redis.redis)
            if job.is_failed or job.is_finished:
                job.delete()
                job = None
        except NoSuchJobError:
            job = None
        if job:
            flash(_(f'Task "{id} is currently pending'))
            return bad_request(f'Task "{id}" in progress')
        else:
            current_app.task_queue.enqueue(f"cloudlight.cloudflask.app.tasks.{id.replace('-','_')}", job_id=id)
            return jsonify({'success': True})

    else:
        id = request.args.get('id', '')
        if not id:
            return bad_request('Task id required')
        try:
            job = Job.fetch(id, connection=g.redis.redis)
        except NoSuchJobError:
            return bad_request('Unknown task')
        status = job.get_status()
        return jsonify({'done': status == 'finished', 'error': status != 'finished',
                        'progress': job.meta.get('progress', 0)})


@bp.route('/service', methods=['POST', 'GET'])
@login_required
def service():
    """start, stop, enable, disable, restart"""
    name = request.args.get('name', '')
    try:
        service = cloudlight_service(name)
    except ValueError:
        return bad_request(f'Service "{name}" does not exist.')
    if request.method == 'POST':
        service.control(request.form['data'])
        return jsonify({'success': True})
    else:
        return jsonify(service.status_dict())


# @bp.route('/favicon.ico')
# def favicon():
#     from flask import send_from_directory
#     return send_from_directory(os.path.join(current_app.root_path, 'static'),
#                                'favicon.ico', mimetype='image/vnd.microsoft.icon')


@bp.route('/status')
@login_required
def status():
    from ....config import REDIS_SCHEMA
    table = [('Setting', 'Value')]
    table += [(k, k, v) for k, v in current_app.redis.read(REDIS_SCHEMA['keys']).items()]
    from datetime import timedelta
    times, vals = list(zip(*g.redis.range('temp:value_avg120000', start=datetime.now()-timedelta(days=1))))
    times = np.array(times, dtype='datetime64[ms]')
    fig = px.line(x=times, y=vals, title='Temps')
    # TODO set data_revision based on time interval
    tempfig = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template('status.html', title=_('Settings'), table=table, tempfig=tempfig)


@bp.route('/settings')
@login_required
def settings():
    return render_template('settings.html', title=_('Settings'))


@bp.route('/off', methods=['POST'])
@login_required
def off():
    g.redis.store('lamp:mode', 'off')
    return jsonify({'success': True})


@bp.route('/help')
@login_required
def help():
    from cloudlight.util import get_services as cloudlight_services
    services = cloudlight_services()
    from rq.job import NoSuchJobError
    try:
        job = Job.fetch('email-logs', connection=g.redis.redis)
        exporting = job.get_status() in ('queued', 'started', 'deferred', 'scheduled')
    except NoSuchJobError:
        exporting = False
    return render_template('help.html', title=_('Help'), services=services.values(), exporting=exporting)


@bp.route('/pihole')
def pihole():
    return redirect('https://cloudlight.local/admin')


@bp.route('/modeform', methods=['POST'])
@login_required
def modeform():
    mode = request.form['data']
    try:
        form = cloudlight.fadecandy.build_form(mode, g.redis)
        return jsonify({'html': render_template('_mode_form.html', form=form, active_mode=g.mode)})
    except KeyError:
        return bad_request(f'"{mode}" is not known')


@bp.route('/notifications')
@login_required
def notifications():
    since = request.args.get('since', 0.0, type=float)
    notifications = current_user.notifications.filter(
        Notification.timestamp > since).order_by(Notification.timestamp.asc())
    return jsonify([{'name': n.name, 'data': n.get_data(), 'timestamp': n.timestamp} for n in notifications])
