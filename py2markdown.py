#!/usr/bin/env python

import sys
import os
import json
import time
from http.server import SimpleHTTPRequestHandler
import argparse
import logging
import socketserver
import tempfile
from http import HTTPStatus

import markdown
from mdx_gfm import GithubFlavoredMarkdownExtension
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, LoggingEventHandler

logging.basicConfig(level=logging.DEBUG,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')

log = logging.getLogger(sys.argv[0])

INITIAL_PORT = 9000

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="eng">
    <head>
        <title>Watching {{filename}}</title>
    </head>
    <body>

    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/4.0.0/github-markdown.min.css" integrity="sha512-Oy18vBnbSJkXTndr2n6lDMO5NN31UljR8e/ICzVPrGpSud4Gkckb8yUpqhKuUNoE+o9gAb4O/rAxxw1ojyUVzg==" crossorigin="anonymous" referrerpolicy="no-referrer" />
    <style>
        .markdown-body {
            box-sizing: border-box;
            min-width: 200px;
            max-width: 980px;
            margin: 0 auto;
            padding: 45px;
        }

        @media (max-width: 767px) {
            .markdown-body {
                padding: 15px;
            }
        }
    </style>
    <article id="content" class="markdown-body">{{content}}</article>
    <script>
    setInterval(function(){
        fetch(window.location.href + 'content')
        .then(res => res.json())
        .then((out) => {
            document.getElementById("content").innerHTML = out['converted'];
            }).catch(err => { throw err }); }, 300);
    </script>
    </body>
</html>
'''

watching_file = None
converted_content = None

def convert_file_to_html_and_save_to_memory(file_name):
    global converted_content
    with open(file_name, 'r') as markdown_file:
        converted_content = markdown.markdown(
                markdown_file.read(), extensions=[GithubFlavoredMarkdownExtension()])
    log.debug('converted file %s' % file_name)

class UpdateHTMLContentEventHandler(FileSystemEventHandler):
    """Logs all the events captured."""

    def on_modified(self, event):
        global last_update
        super().on_modified(event)
        if event.src_path != watching_file:
            return

        convert_file_to_html_and_save_to_memory(event.src_path)
        log.debug('updated modified file %s' % watching_file)

def watch_file_and_convert_on_updates(file_name):
    file_path = os.path.dirname(file_name)
    if file_path == '':
        file_path = '.'
    observer = Observer()
    observer.schedule(UpdateHTMLContentEventHandler(), file_path, recursive=False)
    observer.start()
    log.debug('watching file %s' % file_name)
    return observer

class ContentHTTPRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/content':
            response_content = json.dumps({"converted": converted_content})
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-type", "application/json")
            self.send_header("Content-Length", len(response_content))
            self.end_headers()
            self.wfile.write(response_content.encode('utf-8'))
            return

        f = self.send_head()
        if f:
            try:
                html_content = HTML_TEMPLATE\
                        .replace('{{filename}}', watching_file)\
                        .replace('{{content}}', converted_content)
                self.wfile.write(html_content.encode('utf-8'))
            finally:
                f.close()

if __name__ == '__main__':
    # Parser options
    parser = argparse.ArgumentParser(description='Convert Markdown file to HTML and serve in a HTTP server')
    parser.add_argument('file', help='file to convert')
    args = parser.parse_args()

    watching_file = os.path.abspath(args.file)

    # Initial conversion
    convert_file_to_html_and_save_to_memory(watching_file)

    # Watch file and convert
    observer = watch_file_and_convert_on_updates(watching_file)

    # Start HTTP server
    handler = ContentHTTPRequestHandler
    while True:
        try:
            with socketserver.TCPServer(("", INITIAL_PORT), handler) as httpd:
                print("Server started at http://localhost:%s" % INITIAL_PORT)
                httpd.serve_forever()
        except OSError as err:
            print(err)
            INITIAL_PORT += 1
        finally:
            observer.stop()
            observer.join()
