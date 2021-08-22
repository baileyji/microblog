from datetime import datetime

import numpy as np
from flask import render_template, flash, redirect, url_for, request, g, \
    jsonify, current_app, Response, copy_current_request_context
from flask_login import current_user, login_required
from flask_babel import _, get_locale

import cloudlight.fadecandy
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
from .helpers import *


def guess_language(x):
    return 'en'


@bp.before_app_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
    g.locale = str(get_locale())
    g.redis = current_app.redis
    g.mode = current_app.redis.read('lamp:mode')


@bp.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store'
    return response


@bp.route('/', methods=['GET', 'POST'])
@bp.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    # form = PostForm()
    # if form.validate_on_submit():
    #     language = guess_language(form.post.data)
    #     if language == 'UNKNOWN' or len(language) > 5:
    #         language = ''
    #     post = Post(body=form.post.data, author=current_user, language=language)
    #     db.session.add(post)
    #     db.session.commit()
    #     flash(_('Your post is now live!'))
    #     return redirect(url_for('main.index'))
    # page = request.args.get('page', 1, type=int)
    # posts = current_user.followed_posts().paginate(page, current_app.config['POSTS_PER_PAGE'], False)
    # next_url = url_for('main.index', page=posts.next_num) if posts.has_next else None
    # prev_url = url_for('main.index', page=posts.prev_num) if posts.has_prev else None
    # return render_template('index.html', title=_('Home'), form=form, posts=posts.items, next_url=next_url,
    #                        prev_url=prev_url)

    from cloudlight.fadecandy import EFFECTS
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


@bp.route('/off')
@login_required
def off():
    return index()


@bp.route('/help')
@login_required
def help():
    return render_template('help.html', title=_('Help'))


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
