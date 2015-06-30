# -*- coding: utf-8 -*-
from email.utils import formataddr
from functools import partial

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import ugettext, ugettext_lazy as _

from djangocms_text_ckeditor.fields import HTMLField

from aldryn_forms.models import FormPlugin

from emailit.api import construct_mail

from .helpers import get_theme_template_name, render_text


EMAIL_THEMES = getattr(
    settings,
    "ALDRYN_FORMS_EMAIL_THEMES",
    [('default', _('default'))]
)


class EmailNotificationFormPlugin(FormPlugin):

    class Meta:
        proxy = True

    def copy_relations(self, oldinstance):
        for item in oldinstance.email_notifications.all():
            item.pk = None
            item.form = self
            item.save()


class EmailNotification(models.Model):
    theme = models.CharField(
        verbose_name=_('theme'),
        max_length=200,
        help_text=_('Provides the base theme for the email.'),
        choices=EMAIL_THEMES
    )
    to_name = models.CharField(
        verbose_name=_('to name'),
        max_length=200,
        blank=True
    )
    to_email = models.CharField(
        verbose_name=_('to email'),
        max_length=200,
        blank=True
    )
    to_user = models.ForeignKey(
        to=getattr(settings, 'AUTH_USER_MODEL', 'auth.User'),
        verbose_name=_('to user'),
        blank=True,
        null=True,
        limit_choices_to={'is_staff': True},
    )
    from_name = models.CharField(
        verbose_name=_('from name'),
        max_length=200,
        blank=True
    )
    from_email = models.CharField(
        verbose_name=_('from email'),
        max_length=200,
        blank=True
    )
    subject = models.CharField(
        verbose_name=_("subject"),
        max_length=200,
        blank=True
    )
    body_text = models.TextField(
        verbose_name=_('email body (txt)'),
        blank=True,
        help_text=_('used when rendering the email in text only mode.')
    )
    body_html = HTMLField(
        verbose_name=_('email body (html)'),
        blank=True,
        help_text=_('used when rendering the email in html.')
    )
    form = models.ForeignKey(
        to=EmailNotificationFormPlugin,
        related_name='email_notifications'
    )

    def __unicode__(self):
        to_name = self.get_recipient_name()
        to_email = self.get_recipient_email()
        return u'{0} ({1})'.format(to_name, to_email)

    def clean(self):
        recipient_email = self.get_recipient_email()

        if self.pk and not recipient_email:
            message = ugettext('Please provide a recipient.')
            raise ValidationError(message)

    def get_text_variable_choices(self):
        return list(self.form.get_form_fields_as_choices())

    def get_recipient_name(self):
        if self.to_name:
            # manual name takes precedence over user relationship.
            name = self.to_name
        elif self.to_user_id:
            name = self.to_user.get_full_name()
        else:
            name = ''
        return name

    def get_recipient_email(self):
        if self.to_email:
            # manual email takes precedence over user relationship.
            email = self.to_email
        elif self.to_user_id:
            email = self.to_user.email
        else:
            email = ''
        return email

    def get_email_context(self, form):
        get_template = partial(get_theme_template_name, theme=self.theme)

        context = {
            'form_plugin': self.form,
            'form_data': form.get_serialized_field_choices(),
            'form_name': self.form.name,
            'email_notification': self,
            'email_html_theme': get_template(format='html'),
            'email_txt_theme': get_template(format='txt'),
        }
        return context

    def get_email_kwargs(self, form):
        text_context = form.get_cleaned_data()
        text_context['form_name'] = self.form.name

        email_context = self.get_email_context(form)
        email_context['text_context'] = text_context

        kwargs = {
            'context': email_context,
            'language': self.form.language,
            'template_base': 'aldryn_forms/email_notifications/emails/notification',
        }

        render = partial(render_text, context=text_context)

        recipient_name = self.get_recipient_name()

        recipient_email = self.get_recipient_email()
        recipient_email = render(recipient_email)

        if recipient_name:
            recipient_name = render(recipient_name)
            recipient_email = formataddr((recipient_name, recipient_email))

        kwargs['recipients'] = [recipient_email]

        if self.from_email:
            from_email = render(self.from_email)

            if self.from_name:
                from_name = render(self.from_name)
                from_email = formataddr((from_name, from_email))

            kwargs['from_email'] = from_email
        return kwargs

    def prepare_email(self, form):
        email_kwargs = self.get_email_kwargs(form)
        return construct_mail(**email_kwargs)

    def render_body_text(self, context):
        return render_text(self.body_text, context)

    def render_body_html(self, context):
        return render_text(self.body_html, context)

    def render_subject(self, context):
        return render_text(self.subject, context)
