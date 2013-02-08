#!/usr/bin/env python

# http://gerrit-documentation.googlecode.com/svn/Documentation/2.2.2/cmd-
# query.html

import pkg_resources
import subprocess
from datetime import datetime
import simplejson as json
import time
import tempfile
import textwrap
import os


class FGerrit(object):

    def __init__(self, ssh_user, ssh_host, project, ssh_port=29418,
                 status="open"):
        self.ssh_user = ssh_user
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.project = project
        self.status = status
        self.full_width = int(os.popen('stty size', 'r').read().split()[1])

    def _conv_ts(self, timestamp, terse=False):
        if terse:
            when = time.time() - timestamp
            if when < 60:
                return '%4.1fs' % when
            elif when < 3600:
                return '%4.1fm' % (when / 60)
            elif when < 86400:
                return '%4.1fh' % (when / 3600)
            else:
                return '%4.1fd' % (when / 86400)
        else:
            return datetime.fromtimestamp(int(timestamp))

    def _run_query(self, qargs, plain=False):
        if not plain:
            sshcmd = 'ssh -p %d %s@%s "gerrit query --format=JSON %s"' % \
                (self.ssh_port, self.ssh_user, self.ssh_host, qargs)
        else:
            sshcmd = 'ssh -p %d %s@%s "gerrit query --format=TEXT %s"' % \
                (self.ssh_port, self.ssh_user, self.ssh_host, qargs)
        p = subprocess.Popen(sshcmd, shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        retval = p.wait()
        if retval != 0:
            raise Exception('Error on ssh to gerrit %s' % p.stdout.readlines())
        if not plain:
            result = []
            for line in p.stdout.readlines():
                result.append(json.loads(line))
            retval = p.wait()
            return [x for x in result if 'status' in x]
        else:
            return " ".join(p.stdout.readlines())

    def _run_cmd(self, cargs):
        sshcmd = "ssh -p %d %s@%s 'gerrit %s'" % (self.ssh_port, self.ssh_user, self.ssh_host, cargs.replace("'", "'\"'\"'"))
        p = subprocess.Popen(sshcmd, shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        retval = p.wait()
        if retval != 0:
            raise Exception('Error on ssh to gerrit %s' % p.stdout.readlines())
        return " ".join(p.stdout.readlines())

    def list_reviews(self):
        return self._run_query(
            'status:%s project:%s --current-patch-set' % (self.status,
                                                          self.project))

    def _parse_approvals(self, review):
        retval = [' ', ' ', ' ']
        for i in review.get('currentPatchSet', {}).get('approvals', []):
            typ = i['type']
            idx = {'VRIF': 0, 'CRVW': 1, 'APRV': 2}.get(typ)
            if idx is not None:
                val = int(i['value'])
                if val < 0:
                    retval[idx] = '-'
                elif typ == 'CRVW':
                    if val > 1 and retval[idx] == ' ':
                        retval[idx] = '+'
                elif val > 0 and retval[idx] == ' ':
                    retval[idx] = '+'
        return retval

    def get_review(self, review_id, comments=False, text=False):
        """Either a short id (5264) or long hash"""
        if comments:
            return self._run_query('%s --current-patch-set --comments --commit-message' % review_id, plain=text)
        else:
            return self._run_query(review_id, plain=text)

    def delete_change(self, patchset):
        payload = "review %s --delete" % patchset
        return self._run_cmd(payload)

    def abandon_change(self, patchset):
        payload = "review %s --abandon" % patchset
        return self._run_cmd(payload)

    def restore_change(self, patchset):
        payload = "review %s --restore" % patchset
        return self._run_cmd(payload)

    def get_message(self, message):
        if not message:
            editor = os.environ.get(
                'FGERRIT_EDITOR', os.environ.get('EDITOR', 'vi'))
            with tempfile.NamedTemporaryFile() as fp:
                p = subprocess.Popen('%s %s' % (editor, fp.name), shell=True)
                retval = p.wait()
                if retval != 0:
                    raise Exception('Error on editor exit code %d' % retval)
                message = fp.read().strip()
            if not message:
                raise Exception('Abort, no message')
        return "'%s'" % message.replace("'", "'\"'\"'")

    def post_message(self, review_id, message):
        if not message:
            raise Exception('Abort, no message')
        payload = "review %s --message=%s" % (review_id, message)
        return self._run_cmd(payload)

    def verify_change(self, review_id, score, message=None):
        valid_scores = ["-1", "0", "+1"]
        if message:
            payload = "review %s --verified %s --message='%s'" % (review_id,
                                                                  score,
                                                                  message)
        else:
            payload = "review %s --verified %s" % (review_id, score)
        if score in valid_scores:
            return self._run_cmd(payload)
        else:
            raise Exception(
                'Score should be one of: %s' % ' '.join(valid_scores))

    def code_review(self, review_id, score, message=None):
        valid_scores = ["-2", "-1", "0", "+1", "+2"]
        if message:
            payload = "review %s --code-review %s --message=%s" % (
                review_id, score, message)
        else:
            payload = "review %s --code-review %s" % (review_id, score)
        if score in valid_scores:
            return self._run_cmd(payload)
        else:
            raise Exception(
                'Score should be one of: %s' % ' '.join(valid_scores))

    def approve_review(self, review_id, score, message=None):
        valid_scores = ["0", "+1"]
        if message:
            payload = "approve %s --approve %s --message='%s'" % (review_id,
                                                                  score,
                                                                  message)
        else:
            payload = "approve %s --approve %s" % (review_id, score)
        if score in valid_scores:
            return self._run_cmd(payload)
        else:
            raise Exception(
                'Score should be one of: %s' % ' '.join(valid_scores))

    def print_reviews_list(self, reviews):
        title = "Open Reviews for %s" % self.project
        tlen = len(title)
        sep = "=" * (self.full_width - 1)
        print sep
        print title + " " * (self.full_width - tlen - 1)
        print sep
        print 'ID       When  VCA  Submitter: Description'
        sep = "-" * (self.full_width - 1)
        print sep
        for r in reviews:
            v, c, a = self._parse_approvals(r)
            print '%s  %s  %s%s%s  %s' % (
                r['id'][:6],
                self._conv_ts(r['lastUpdated'], terse=True),
                v, c, a,
                self.rewrap('%s <%s>: %s' % (
                    r['owner']['name'],
                    r['owner']['username'],
                    r['subject']), 20))
            print sep

    def print_review_comments(self, review):
        for comment in review[0]['comments']:
            print "=" * 25
            print "%s - %s:" % (self._conv_ts(comment['timestamp']),
                                comment['reviewer']['username'])
            print ""
            print comment['message']
            print ""

    def rewrap(self, text, indent):
        text_width = self.full_width - indent - 1
        indention = '\n' + ' ' * indent
        return indention.join(
            indention.join(textwrap.wrap(v, width=text_width))
            for v in text.split('\n')
        )

    def print_review(self, review_id):
        data = self.get_review(review_id, comments=True)[0]
        out = [
            ('Owner',
             '%s <%s>' % (data['owner']['name'], data['owner']['username']))]
        if data['branch'] != 'master':
            out.append(('TARGETED BRANCH', data['branch']))
        out.extend([
            ('Patch Set Number', data['currentPatchSet']['number']),
            ('Patch Set Date',
             time.asctime(time.localtime(int(data['currentPatchSet']['createdOn'])))),
            ('Patch Set Id', data['currentPatchSet']['revision'][:5])])
        approvals = []
        for approval in data['currentPatchSet'].get('approvals', []):
            approvals.append('%+d %s' % (int(approval['value']),
                             approval['by']['username']))
        out.extend([
            ('Status', ', '.join(sorted(approvals))),
            ('Commit Message', data['commitMessage'].strip())])
        for comment in data.get('comments', []):
            out.extend([
                ('Reviewer',
                 '%s <%s>' % (comment['reviewer']['name'],
                              comment['reviewer']['username'])),
                ('Date',
                 time.asctime(time.localtime(int(comment['timestamp'])))),
                ('Comment', comment['message'].strip())])
        tlen = max(len(t) for t, v in out)
        sep = '-' * (self.full_width - 1)
        print sep
        for title, value in out:
            if title == 'Reviewer':
                print sep
            print (
                '%%0%ds  %%s' % tlen) % (title, self.rewrap(value, tlen + 2))
        print sep

    def checkout(self, change_id):
        if 'git-review' not in pkg_resources.working_set.by_key:
            raise Exception('git-review is not installed')
        data = self.get_review(change_id, comments=True)[0]
        cmd = ['git', 'review', '--download', data['id']]
        error_code = subprocess.Popen(cmd).wait()
        if error_code != 0:
            raise Exception('Error code %d from %s' % (error_code, cmd))

    def submit(self):
        if 'git-review' in pkg_resources.working_set.by_key:
            raise Exception('git-review is not installed')
        cmd = ['git', 'review']
        error_code = subprocess.Popen(cmd).wait()
        if error_code != 0:
            raise Exception('Error code %d from %s' % (error_code, cmd))

    def draft(self):
        if 'git-review' not in pkg_resources.working_set.by_key:
            raise Exception('git-review is not installed')
        cmd = ['git', 'review', '--draft']
        error_code = subprocess.Popen(cmd).wait()
        if error_code != 0:
            raise Exception('Error code %d from %s' % (error_code, cmd))
