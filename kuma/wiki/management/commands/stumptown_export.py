"""
Dump wiki documents to .json files that stumptown-renderer can read.
"""
from __future__ import division, unicode_literals, print_function

import datetime
import errno
import json
import logging
import os
import urlparse
from math import ceil

from celery import chain
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from kuma.core.utils import chunked
from kuma.wiki.jobs import DocumentContributorsJob
from kuma.wiki.models import Document
from kuma.wiki.templatetags.jinja_helpers import absolutify


# XXX stop using logging and use self.stdout
# https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/
log = logging.getLogger('kuma.wiki.management.commands.stumptown_export')


# XXX Delete an use `os.makedirs(directory, exist_ok=True)` when in py 3
def makedirs(directory):
    try:
        os.makedirs(directory)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def export_document(doc, outdir, base_url, force=False, ensure_contributors=False):
    print(repr(doc), base_url)
    # XXX will need to include locale later
    destination = os.path.join(outdir, doc.slug) + '.json'
    if os.path.isfile(destination) and not force:
        log.info('Already created {}'.format(destination))
        print("UGH!?")
        return

    # XXX might need to get smarter
    assert not doc.is_template
    assert not doc.is_redirect
    assert not doc.deleted

    makedirs(os.path.dirname(destination))

    # These lines are copied from kuma.api.v1.views.document_api_data()
    job = DocumentContributorsJob()
    job.fetch_on_miss = ensure_contributors
    contributors = [c['username'] for c in job.get(doc.pk)]

    document = {
        'legacy': True,
        # 'related_content': doc.quick_links_html,
        'related_content': doc.get_quick_links_html(),
        'title': doc.title,
        'mdn_url': urlparse.urljoin(base_url, doc.get_absolute_url()),
        # Should we perhaps read from doc.json instead??
        # 'body': doc.body_html,
        'body': doc.get_body_html(),  # XXX better?
        'contributors': contributors,
    }
    # from pprint import pprint
    # pprint(json.loads(doc.json))
    # print('----------------------------------------------')

    with open(destination, 'w') as f:
        json.dump(document, f, indent=2)
    log.info('Created {}'.format(destination))


class Command(BaseCommand):
    args = '<document_path document_path ...>'
    help = 'Dumps rendered wiki documents to a JSON file for Stumptown to read'

    def add_arguments(self, parser):
        parser.add_argument(
            'paths',
            help='Path to document(s), like /en-US/docs/Web',
            nargs='*',  # overridden by --all
            metavar='path')
        parser.add_argument(
            '--all',
            help='Render ALL documents (rather than by path)',
            action='store_true')
        parser.add_argument(
            '--min-age',
            help='Documents rendered less than this many seconds ago will be'
                 ' skipped (default 600)',
            type=int,
            default=600)
        parser.add_argument(
            '--baseurl',
            help='Base URL to site')
        parser.add_argument(
            '--force',
            help='Force rendering, first clearing record of any rendering in'
                 ' progress',
            action='store_true')
        parser.add_argument(
            '--outdir',
            default='wiki-stumptown-export',
            help='Directory to write into (default ./wiki-stumptown-export')

    def handle(self, *args, **options):
        base_url = options['baseurl'] or absolutify('')
        force = options['force']
        outdir = options['outdir']

        if options['all']:
            # Query all documents, excluding those whose `last_rendered_at` is
            # within `min_render_age` or NULL.
            min_render_age = (
                datetime.datetime.now() -
                datetime.timedelta(seconds=options['min_age']))
            docs = Document.objects.filter(
                Q(last_rendered_at__isnull=True) |
                Q(last_rendered_at__lt=min_render_age))
            docs = docs.order_by('-modified')
            docs = docs.values_list('id', flat=True)

            self.chain_render_docs(docs, outdir, base_url, force)

        else:
            # Accept page paths from command line, but be liberal
            # in what we accept, eg: /en-US/docs/CSS (full path);
            # /en-US/CSS (no /docs); or even en-US/CSS (no leading slash)
            paths = options['paths']
            if not paths:
                raise CommandError('Need at least one document path to render')
            for path in paths:
                if path.startswith('/'):
                    path = path[1:]
                locale, sep, slug = path.partition('/')
                head, sep, tail = slug.partition('/')
                if head == 'docs':
                    slug = tail
                doc = Document.objects.get(locale=locale, slug=slug)
                log.info(
                    u'Stumptown exporting %s (%s)' % (doc, doc.get_absolute_url()))
                export_document(doc, outdir, base_url, force)

    def chain_render_docs(self, docs, outdir, base_url, force):
        tasks = []
        count = 0
        total = len(docs)
        n = int(ceil(total / 5))
        chunks = chunked(docs, n)

        for chunk in chunks:
            count += len(chunk)
            tasks.append(
                export_document_chunk.si(chunk, base_url, force))

        # Make it so.
        chain(*tasks).apply_async()
