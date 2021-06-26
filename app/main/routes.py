from datetime import datetime

import numpy as np
from flask import render_template, flash, redirect, url_for, request, g, \
    jsonify, current_app, Response
from flask_login import current_user, login_required
from flask_babel import _, get_locale
from .. import db
from .forms import EditProfileForm, EmptyForm, PostForm, SearchForm, MessageForm
from ..models import User, Post, Message, Notification
from ..translate import translate
from . import bp
from ..api.errors import bad_request


def guess_language(x):
    return 'en'


@bp.before_app_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        # g.search_form = SearchForm()
    g.locale = str(get_locale())
    g.redis = current_app.redis

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
    posts = current_user.followed_posts().paginate(
        page, current_app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('main.index', page=posts.next_num) \
        if posts.has_next else None
    prev_url = url_for('main.index', page=posts.prev_num) \
        if posts.has_prev else None
    return render_template('index.html', title=_('Home'), form=form,
                           posts=posts.items, next_url=next_url,
                           prev_url=prev_url)


@bp.route('/redis', methods=['POST', 'GET'])
@login_required
def redis():
    if request.method == 'POST':
        try:
            current_app.redis.store(request.form['source'].partition(':')[2], request.form['value'])
            return jsonify({'success': True})
        except:
            current_app.logger.error('post error', exc_info=True)
    else:
        try:
            return jsonify({'value': current_app.redis.read(request.args.get('key'))})
        except:
            current_app.logger.error(f'get error {request.args}', exc_info=True)
    return bad_request('control failed')


def event_stream():
    for _, v in current_app.redis.listen('chat'):
        yield f'data: {v}\n\n'


def get_status_info(redis):
    keys = ('master_vol', 'speaker_status', 'master_brightness')
    names = ('master_vol', 'Brightness', 'Many', 'Other', 'Settings')
    return {k: str(np.random.uniform()) for k in keys}
    # return redis.read(keys, error_missing=False)


def get_plot_data(redis, id, t0, t1):
    import plotly
    import plotly.express as px
    import json
    import numpy as np
    # times, vals = redis.redis_ts.read(id, t0, t1)
    times=np.arange(100)+132
    vals=np.random.uniform(size=100)
    # plot_data = [{'x': times,'y': vals,'name': title}]
    # plot_layout = {'title': title}
    # plot_config = {'responsive': True}
    # d = json.dumps(plot_data, cls=plotly.utils.PlotlyJSONEncoder)
    # l = json.dumps(plot_layout, cls=plotly.utils.PlotlyJSONEncoder)
    # c = json.dumps(plot_config, cls=plotly.utils.PlotlyJSONEncoder)

    fig = px.line(x=times, y=vals, title='Temps')
    fig.layout.datarevision = t0
    # set data_revision based on time interval
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

_foo=0
def get_plot_points_since(redis, id, t0):
    # new = redis.redis_ts.read(id, t0)
    import json
    global _foo

    new = np.arange(100) + _foo, np.random.uniform(size=100)
    _foo +=100
    return {'x': new[0].tolist(), 'y': new[1].tolist()}


import queue
class MessageAnnouncer:
    def __init__(self):
        self.listeners = []

    def listen(self):
        self.listeners.append(queue.Queue(maxsize=5))
        return self.listeners[-1]

    def announce(self, msg):
        # We go in reverse order because we might have to delete an element, which will shift the
        # indices backward
        from logging import getLogger
        # getLogger(__name__).info(f'Announcing {msg}')
        for i in reversed(range(len(self.listeners))):
            try:
                self.listeners[i].put_nowait(msg)
            except queue.Full:
                del self.listeners[i]


announcer = MessageAnnouncer()


def datagen(redis):
    elapsed=0
    plotid = 'temp-plot'
    import json, time
    while True:
        if not elapsed%2:
            event = 'update'
            data = get_status_info(redis)
        elif not elapsed%23:
            event = 'plotupdate'
            data = {'id': plotid, 'kind': 'full', 'data': get_plot_data(redis, plotid, 0, 1)}
        elif not elapsed%3:
            event = 'plotupdate'
            data = {'id': plotid, 'kind': 'partial', 'data': get_plot_points_since(redis, plotid, 0)}

        announcer.announce(f"event:{event}\nretry:5\ndata: {json.dumps(data)}\n\n")
        time.sleep(1)
        elapsed+=1


@bp.route('/stream',  methods=['GET'])
@login_required
def stream():
    import time, json, threading
    try:
        g.datathread
    except AttributeError:
        g.datathread = threading.Thread(target=datagen, args=(current_app.redis,), daemon=True)
        g.datathread.start()

    def event_stream():
        messages = announcer.listen()  # returns a queue.Queue
        while True:
            yield messages.get()  # blocks until a new message arrives
    return current_app.response_class(event_stream(), mimetype="text/event-stream")


@bp.route('/lamp')
@login_required
def lamp():
    modes = ('Lamp', 'Starfall', 'Fireplace', 'Acidtrip')
    from .forms import LampForm, StarfallForm, MasterControlForm
    return render_template('lamp.html', title=_('Lamp'), modes=modes, masterform=MasterControlForm(),
                           form=StarfallForm())


@bp.route('/status')
@login_required
def status():
    from .forms import MasterControlForm
    table = [('Setting', 'Value')]
    table += [(k, k, v) for k, v in get_status_info(current_app.redis).items()]


    import plotly
    import plotly.express as px
    import numpy as np
    import json
    times=np.arange(100)+132
    vals=np.random.uniform(size=100)
    # plot_data = [{'x': times,'y': vals,'name': title}]
    # plot_layout = {'title': title}
    # plot_config = {'responsive': True}
    # d = json.dumps(plot_data, cls=plotly.utils.PlotlyJSONEncoder)
    # l = json.dumps(plot_layout, cls=plotly.utils.PlotlyJSONEncoder)
    # c = json.dumps(plot_config, cls=plotly.utils.PlotlyJSONEncoder)

    fig = px.line(x=times, y=vals, title='Temps')
    # set data_revision based on time interval
    tempfig = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template('status.html', title=_('Settings'), table=table,
                           masterform=MasterControlForm(),
                           tempfig=tempfig)



@bp.route('/plot', methods=['POST'])
def plot():

    plot_name = request.form['name']
    import plotly
    import plotly.express as px
    import numpy as np
    import json
    times=np.arange(100)+132
    vals=np.random.uniform(size=100)
    # plot_data = [{'x': times,'y': vals,'name': title}]
    # plot_layout = {'title': title}
    # plot_config = {'responsive': True}
    # d = json.dumps(plot_data, cls=plotly.utils.PlotlyJSONEncoder)
    # l = json.dumps(plot_layout, cls=plotly.utils.PlotlyJSONEncoder)
    # c = json.dumps(plot_config, cls=plotly.utils.PlotlyJSONEncoder)

    fig = px.line(x=times, y=vals, title='Temps', responsive=True)
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)



@bp.route('/modeform', methods=['POST'])
@login_required
def modeform():
    from .forms import LampForm, StarfallForm, FireplaceForm, AcidtripForm
    forms = {'Lamp': LampForm,
             'Starfall': StarfallForm,
             'Fireplace': FireplaceForm,
             'Acidtrip': AcidtripForm}
    mode = request.form['text']
    return jsonify({'html': render_template('_mode_form.html', mode=mode, form=forms[mode]())})



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
