from datetime import datetime

import numpy as np
from flask import render_template, flash, redirect, url_for, request, g, \
    jsonify, current_app, Response, copy_current_request_context
from flask_login import current_user, login_required
from flask_babel import _, get_locale

import cloudlight.fadecandy
from .. import db
from .forms import EditProfileForm, EmptyForm, PostForm, SearchForm, MessageForm
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
    form = PostForm()
    if form.validate_on_submit():
        language = guess_language(form.post.data)
        if language == 'UNKNOWN' or len(language) > 5:
            language = ''
        post = Post(body=form.post.data, author=current_user, language=language)
        db.session.add(post)
        db.session.commit()
        flash(_('Your post is now live!'))
        return redirect(url_for('main.index'))
    page = request.args.get('page', 1, type=int)
    posts = current_user.followed_posts().paginate(page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.index', page=posts.next_num) if posts.has_next else None
    prev_url = url_for('main.index', page=posts.prev_num) if posts.has_prev else None
    return render_template('index.html', title=_('Home'), form=form, posts=posts.items, next_url=next_url,
                           prev_url=prev_url)


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
    # @copy_current_request_context
    def _stream():
        for k, v in clr.redis.listen(REDIS_SCHEMA['keys']):
            event = 'update'
            data = {k: v}

            # plotid = 'temp:value'
            # since = None
            # kind = 'full' if since is None else 'partial'
            # new = list(zip(*redis.range(plotid, since)))
            # data = {'id': f'redisplot:{plotid}', 'kind': kind, 'data': {'x': new[0], 'y': new[1]}}

            msg = f"event:{event}\nretry:5\ndata: {json.dumps(data)}\n\n"
            yield msg
    return current_app.response_class(_stream(), mimetype="text/event-stream")



@bp.route('/status')
@login_required
def status():
    from ....config import REDIS_SCHEMA
    table = [('Setting', 'Value')]
    table += [(k, k, v) for k, v in current_app.redis.read(REDIS_SCHEMA['keys']).items()]

    times, vals = list(zip(*g.redis.range('temp:value_avg120000')))
    times = np.array(times,dtype='datetime64[ms]')
    fig = px.line(x=times, y=vals, title='Temps')
    # TODO set data_revision based on time interval
    tempfig = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template('status.html', title=_('Settings'), table=table, tempfig=tempfig)


@bp.route('/lamp', methods=['GET', 'POST'])
@login_required
def lamp():
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

    return render_template('lamp.html', title=_('Lamp'), modes=modes, form=f, active_mode=g.mode)


@bp.route('/modeform', methods=['POST'])
@login_required
def modeform():
    mode = request.form['data']
    try:
        form = cloudlight.fadecandy.build_form(mode, g.redis)
        return jsonify({'html': render_template('_mode_form.html', form=form, active_mode=g.mode)})
    except KeyError:
        return bad_request(f'"{mode}" is not known')


@bp.route('/user/<username>')
@login_required
def user(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    posts = user.posts.order_by(Post.timestamp.desc()).paginate(
        page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.user', username=user.username,
                       page=posts.next_num) if posts.has_next else None
    prev_url = url_for('main.user', username=user.username,
                       page=posts.prev_num) if posts.has_prev else None
    form = EmptyForm()
    return render_template('user.html', user=user, posts=posts.items,
                           next_url=next_url, prev_url=prev_url, form=form)




@bp.route('/follow/<username>', methods=['POST'])
@login_required
def follow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=username).first()
        if user is None:
            flash(_('User %(username)s not found.', username=username))
            return redirect(url_for('main.index'))
        if user == current_user:
            flash(_('You cannot follow yourself!'))
            return redirect(url_for('main.user', username=username))
        current_user.follow(user)
        db.session.commit()
        flash(_('You are following %(username)s!', username=username))
        return redirect(url_for('main.user', username=username))
    else:
        return redirect(url_for('main.index'))




@bp.route('/translate', methods=['POST'])
@login_required
def translate_text():
    return jsonify({'text': translate(request.form['text'],
                                      request.form['source_language'],
                                      request.form['dest_language'])})


@bp.route('/search')
@login_required
def search():
    if not g.search_form.validate():
        return redirect(url_for('main.explore'))
    page = request.args.get('page', 1, type=int)
    posts, total = Post.search(g.search_form.q.data, page,
                               current_app.config['POSTS_PER_PAGE'])
    next_url = url_for('main.search', q=g.search_form.q.data, page=page + 1) \
        if total > page * current_app.config['POSTS_PER_PAGE'] else None
    prev_url = url_for('main.search', q=g.search_form.q.data, page=page - 1) \
        if page > 1 else None
    return render_template('search.html', title=_('Search'), posts=posts,
                           next_url=next_url, prev_url=prev_url)


@bp.route('/messages')
@login_required
def messages():
    current_user.last_message_read_time = datetime.utcnow()
    current_user.add_notification('unread_message_count', 0)
    db.session.commit()
    page = request.args.get('page', 1, type=int)
    messages = current_user.messages_received.order_by(
        Message.timestamp.desc()).paginate(
            page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.messages', page=messages.next_num) \
        if messages.has_next else None
    prev_url = url_for('main.messages', page=messages.prev_num) \
        if messages.has_prev else None
    return render_template('messages.html', messages=messages.items,
                           next_url=next_url, prev_url=prev_url)


@bp.route('/export_posts')
@login_required
def export_posts():
    if current_user.get_task_in_progress('export_posts'):
        flash(_('An export task is currently in progress'))
    else:
        current_user.launch_task('export_posts', _('Exporting posts...'))
        db.session.commit()
    return redirect(url_for('main.user', username=current_user.username))


@bp.route('/notifications')
@login_required
def notifications():
    since = request.args.get('since', 0.0, type=float)
    notifications = current_user.notifications.filter(
        Notification.timestamp > since).order_by(Notification.timestamp.asc())
    return jsonify([{
        'name': n.name,
        'data': n.get_data(),
        'timestamp': n.timestamp}
        for n in notifications])
