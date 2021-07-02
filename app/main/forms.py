from flask import request
from flask_wtf import FlaskForm
import wtforms
from wtforms import StringField, SubmitField, TextAreaField, BooleanField
from wtforms.validators import ValidationError, DataRequired, Length, NumberRange
from flask_babel import _, lazy_gettext as _l
from ..models import User

import wtforms.widgets.html5
import wtforms.fields.html5
from wtforms.fields.html5 import DecimalRangeField


class MasterControlForm(FlaskForm):
    volume = DecimalRangeField('Volume', validators=[NumberRange(min=0, max=1)],
                               id='redisinput:master_vol')
    brightness = DecimalRangeField('Brightness', validators=[NumberRange(min=0, max=1)],
                                   id="redisinput:masterbrightness")
    mute = BooleanField(_l('Mute'), id="redischange:master_mute")


class ColorField(TextAreaField):
    """Create special ColorField for the color picker"""
    # Set the widget for this custom field
    widget = wtforms.widgets.html5.ColorInput()


class CloudControl(FlaskForm):
    speaker_connected = BooleanField()
    muted = BooleanField()


# def select_form_factory(keystr, name):
#     from wtforms.widgets.html5 import ColorInput
#     from wtforms import SelectField, SubmitField, StringField, RadioField
#
#     # def make_select_fields(key, label):
#     #     field = SelectField(f"{label}", choices=list(COMMAND_DICT[key]['vals'].keys()), id=key)
#     #     submit = SubmitField("Update", id=key)
#     #     return field, submit
#     #
#     # def make_string_fields(key, label):
#     #     field = StringField(f"{label}", id=key)
#     #     submit = SubmitField("Update")
#     #     return field, submit
#
#     class Form(FlaskForm):
#         color = wtforms.widgets.html5.ColorInput()
#         brightness = wtforms.fields.html5.DecimalRangeField()
#         remember_me = BooleanField(_l('Remember Me'))
#         submit = SubmitField("Update", id=key)
#
#
#     # for key, value in record.items():
#     #     setattr(Form, key, StringField(value))
#
#     return Form




class LampForm(FlaskForm):
    color = ColorField()
    brightness = DecimalRangeField()
    jazz = BooleanField(_l('Jazzify?'))
    submit = SubmitField("Activate!")


class FireplaceForm(FlaskForm):
    brightness = wtforms.fields.html5.DecimalRangeField()
    temp = wtforms.fields.html5.DecimalRangeField()
    jazz = BooleanField(_l('Jazzify?'))
    submit = SubmitField("Activate!")


class StarfallForm(FlaskForm):
    brightness = wtforms.fields.html5.DecimalRangeField()
    rate = wtforms.fields.html5.DecimalRangeField()
    jazz = BooleanField(_l('Jazzify?'))
    submit = SubmitField("Activate!")


class AcidtripForm(FlaskForm):
    brightness = wtforms.fields.html5.DecimalRangeField()
    jazz = BooleanField(_l('Jazzify?'))
    submit = SubmitField("Activate!")


class EditProfileForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired()])
    about_me = TextAreaField(_l('About me'), validators=[Length(min=0, max=140)])
    submit = SubmitField(_l('Submit'))

    def __init__(self, original_username, *args, **kwargs):
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=self.username.data).first()
            if user is not None:
                raise ValidationError(_('Please use a different username.'))


class EmptyForm(FlaskForm):
    submit = SubmitField('Submit')


class PostForm(FlaskForm):
    post = TextAreaField(_l('Say something'), validators=[DataRequired()])
    submit = SubmitField(_l('Submit'))


class SearchForm(FlaskForm):
    q = StringField(_l('Search'), validators=[DataRequired()])

    def __init__(self, *args, **kwargs):
        if 'formdata' not in kwargs:
            kwargs['formdata'] = request.args
        if 'csrf_enabled' not in kwargs:
            kwargs['csrf_enabled'] = False
        super(SearchForm, self).__init__(*args, **kwargs)


class MessageForm(FlaskForm):
    message = TextAreaField(_l('Message'), validators=[DataRequired(), Length(min=1, max=140)])
    submit = SubmitField(_l('Submit'))
