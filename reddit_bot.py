#!/usr/bin/python
import sys
import praw
import re
import random
import os
import pbd
import string
import time
import functools
from joblib import Parallel, delayed, parallel_backend
from threading import Lock, Condition
import tqdm
import fire
import json
import tensorflow as tf
import numpy as np
import pexpect
import itertools
import collections

import model, sample, encoder

def clean_input(s):
    return ''.join(filter(lambda x: x in set(string.printable), s))

class AugSelector(object):
    def __init__(self):
        self.keys = []
        self.len_k = 0
        
    def register(self, acs):
        self.keys.append(acs)
        self.len_k += 1

    def __next__(self):
        while True:
            for ctr in range(self.len_k):
                cur = self.keys[ctr].read()
                if cur is None:
                    continue
                else:
                    yield cur
    def __iter__(self):
        return self
                
class AugComStream(object):
    def __init__(self, sr, fn, skip_existing=True):
        self.subreddit = sr
        self.fileno_i = fn
        self.skip_existing = skip_existing
    
    def __next__(self):
        for c in self.subreddit.stream.comments(skip_existing=self.skip_existing, pause_after=0):
            yield c
    
    def fileno(self):
        return self.fileno_i
    
    def readline(self):
        for c in self.subreddit.stream.comments(skip_existing=self.skip_existing):
            yield c
            
    def read(self, data=None):
        for c in self.subreddit.stream.comments(skip_existing=self.skip_existing):
            yield c
            
    def write(self, data):
        pass
        
    def seek(self, idx):
        pass
        
    def close(self):
        pass

class StreamList():
    def __init__(self):
        self.stream_file = open("/mnt/stream_list.txt", 'r+')
        self.list = self._load()

    def __del__(self):
        self.stream_file.close()

    def _load(self):
        out = []
        for line in self.stream_file:
            out.append(line.strip())
        print("loaded subms", out)
        return out

    def append(self, data):
        self.stream_file.write(str(data)+"\n")
        self.stream_file.flush()
        self.list.append(data)

class GPT2Bot():
    def __init__(self, log):
        self.log = log
        self.lock = Lock()
        self.stream_guy = False
        self.t_man = False
        self.reddit_1 = praw.Reddit('gptbot')
        self.reddit_2 = praw.Reddit('gptbot2')
        self.toggle = True
        self.rexp = re.compile(r"^(.*)gpt-2(.*)finish this(.*)$", re.IGNORECASE|re.DOTALL)
        self.name = self.reddit_1.user.me().name
        self.stream_list = StreamList()
        self.key_word = "gpt-2"
        self.output = None
        self.callback = None
        self.sample = None
        self.id_history = collections.OrderedDict()
        self.check_hist = True
        self.history_lock = Lock()
        self.sel = AugSelector()

    
    def filter_id(self, id):
        if id in self.id_history:
            return True
        else:
            self.history_lock.acquire()
            self.id_history[id] = True
            self.history_lock.release()
            if self.check_hist and len(self.id_history) > 1000:
                self.check_hist = False
                self.history_lock.acquire()
                reversed_s = collections.OrderedDict.fromkeys(reversed(self.id_history), True)
                reversed_t = collections.OrderedDict(itertools.islice(reversed_s.items(), 500))
                self.id_history = collections.OrderedDict.fromkeys(reversed(reversed_t), True)
                self.history_lock.release()
                time.sleep(10)
                self.check_hist = True
            return False
            
    def reddit(self):
        self.toggle = not self.toggle
        return self.reddit_1 if self.toggle else self.reddit_2
        
    def run_loop(self):
        while True:
            try:
                self.run_mt(32)
            except KeyboardInterrupt:
                self.log("\nUser pressed ctrl-c...")
                break

    def get_response(self, input_str):
        sample = str("\n======================================== SAMPLE 1 ========================================  I'm having some trouble understanding you. Make sure you don't have any special characters in your prompt.").encode('utf-8')

        attempts = 0
        while attempts < 5:
            try:
                child = pexpect.spawn('python src/interactive_conditional_samples.py --top_k 40')
                child.expect('Model prompt >>> ')
                child.sendline(clean_input(input_str))
                child.expect('================================================================================')
                sample = child.before[len(input_str):]
                break
            except pexpect.exceptions.EOF:
                child.kill(0)
                attempts += 1
                print("Attempt ", attempts, "failed. Trying again.")
        return sample.decode()

    def clean_response(self, resp, inp, user=None):
        resp = str(resp[92:]).encode('utf-8')
        resp = resp.split('<|endoftext|>'.encode('utf-8'))[0]
        sp = resp.splitlines()
        self.log("Split len", len(sp))
        out = ""

        ctr = 1
        lp = len(sp)
        stop = False
        pref = "**OUTPUT"
        if user is not None:
            pref += " (courtesy of u/" + user.name + "):**"
        else:
            pref += "**"
        iop = "\n"
        for iline in inp.splitlines():
            iop += "> **" + iline.strip() + "** \n"
        while ctr < len(sp):
            if len(sp[0]) > 0 and ord('=') in sp[0][:min(2, len(sp[0]))] and not stop:
                stop = True
                del sp[0]
                if len(sp) < 1 or ctr == (lp-1):
                    break
                lp = len(sp)
            out += "> " + sp[ctr].decode() + "\n"
            ctr += 1
            if len(out) > len(inp):
                break
        if len(out) < 4:
            return ""
        return str(pref + iop + "\n" + out + "\nBeep boop, I'm a bot.")

    def message_guy(self):
        self.log("MESSAGE GUY STARTING\n")
        for message in self.reddit().inbox.unread(limit=None):
            if isinstance(message, praw.models.Message):
                self.log("Found a DM!\n", silent=True)
                cb = ""
                for line in message.body.splitlines():
                    if line.strip():
                        insensitive_hippo = re.compile(re.escape('**INPUT(.*):**'), re.IGNORECASE)
                        insensitive_d = re.compile(re.escape("Beep boop, I'm a bot."), re.IGNORECASE)
                        cb += str(insensitive_hippo.sub('', str(insensitive_d.sub('', line))))
                cb = clean_input(cb)

                if len(cb.strip()) < 2:
                    self.log("Parent comment was empty", silent=True)
                    continue

                self.lock.acquire()
                response = self.clean_response(self.get_response(cb), cb)
                self.log("Bot replying to direct message: "+cb)
                self.log("Response : "+response+"\n------------------------------------------------")
                self.lock.release()

                try:
                    if not response.strip():
                        self.log("Response was empty")
                        continue
                    message.reply(response)
                    message.mark_read()
                except:
                    self.log("An error occured while replying")
                

    def run(self, n_threads, subm):
        def do_work(self, comment):
            if not isinstance(comment, praw.models.Comment):
                return
            if comment.author is None or comment.author.name == self.name:
                return
            if self.rexp.match(clean_input(comment.body)) is None:
                return
            for h in comment.replies:
                if h.author.name == self.name:
                    return
            try:
                cp = comment.parent()

                if isinstance(cp, praw.models.Submission):
                    self.log("Parent was a submission...\n", silent=True)
                    return
                else:
                    for h in cp.replies:
                        if h.author is None:
                            continue
                        if h.author.name == self.name:
                            self.log("Already replied to this comment...\n", silent=True)
                            return
            except:
                self.log("Unknown error occured")
                return
            self.log("Found one!")
            cb = ""
            for line in cp.body.splitlines():
                if line.strip():
                    insensitive_hippo = re.compile(re.escape('**INPUT(.*):**'), re.IGNORECASE)
                    insensitive_d = re.compile(re.escape("Beep boop, I'm a bot."), re.IGNORECASE)
                    cb += str(insensitive_hippo.sub('', str(insensitive_d.sub('', line))))
            cb = clean_input(cb)
            cpl = "https://www.reddit.com" + cp.permalink

            if len(cb.strip()) < 2:
                self.log("Parent comment was empty")
                return
            elif cb.strip() == "[removed]":
                self.log("Parent comment was removed")
                return

            self.lock.acquire()
            response = self.clean_response(self.get_response(cb), cb, comment.author)
            self.log("Bot replying to : "+cb+"\nURL : "+cpl)
            self.log("Response : "+response+"\n------------------------------------------------")
            self.lock.release()
            
            try:
                if not response:
                    self.log("Response was empty")
                    return
                cp.reply(response)
            except:
                self.log("An error occured while replying")
            return

        self.log("Starting Submission Run... "+str(time.time()))
        submission = praw.models.Submission(self.reddit(), id=subm)
        submission.comments.replace_more(limit=None)
        with parallel_backend('threading', n_jobs=n_threads):
            Parallel()(delayed(do_work)(self, comment) for comment in tqdm.tqdm(submission.comments.list()) if comment is not None)
        self.log("SUBMISSION RUN DONE!!!\n\n============================================================\n", flush=True)

    def should_add_to_list(self, subm):
        if self.key_word in subm.title.lower():
            self.lock.acquire()
            self.log("\nFound a new submission about "+self.key_word+"\nURL: "+subm.permalink)
            self.stream_list.append(subm.id)
            self.lock.release()


    def do_work(self, comment):
        if not self.t_man:
            self.t_man = True
            self.log("\n================ RUNNING SUBMISSION SWEEP ================\n\n")
            with parallel_backend('threading', n_jobs=4):
                Parallel()(delayed(self.run)(16, subm) for subm in tqdm.tqdm(self.stream_list.list))
            self.message_guy()
            time.sleep(14400)
            self.t_man = False
        elif not self.stream_guy:
            self.stream_guy = True
            self.log("\n================ RUNNING SUBMISSION STREAM ================\n\n")
            all = self.reddit().subreddit('all')
            with parallel_backend('threading', n_jobs=4):
                Parallel()(delayed(self.should_add_to_list)(submission) for submission in tqdm.tqdm(all.stream.submissions(skip_existing=True)))
        if not isinstance(comment, praw.models.Comment):
            return
        if comment.author is None or comment.author.name == self.name:
            return
        if self.filter_id(comment.id):
            return
        if self.rexp.match(clean_input(comment.body)) is None:
            return
        for h in comment.replies:
            if h.author.name == self.name:
                return
        self.log("Found one!")

        try:
            cp = comment.parent()

            if isinstance(cp, praw.models.Submission):
                self.log("Parent was a submission...\n")
                return
            else:
                cp.refresh()
                for h in cp.replies:
                    if h.author is None:
                        continue
                    if h.author.name == self.name:
                        self.log("Already replied to this comment...\n")
                        return
        except Exception as e:
            self.log("An unknown error occured.\n" + str(e))
            return

        cb = ""
        for line in cp.body.splitlines():
            if line.strip():
                insensitive_hippo = re.compile(re.escape('**OUTPUT(.*):**'), re.IGNORECASE)
                insensitive_s = re.compile(re.escape('> '))
                insensitive_d = re.compile(re.escape("Beep boop, I'm a bot."), re.IGNORECASE)
                cb += str(insensitive_hippo.sub('', str(insensitive_d.sub('', str(insensitive_s.sub('', line.strip())))))) + "\n"
        cb = clean_input(cb)
        cpl = "https://www.reddit.com" + cp.permalink

        if len(cb.strip()) < 1:
            self.log("Parent comment was empty")
            return
        elif cb.strip() == "[removed]":
            self.log("Parent comment was removed")
            return
        response = ""
        try:
            cntr = 0
            while not response:
                if cntr >= 5:
                    raise Exception()
                self.lock.acquire()
                response = self.clean_response(self.get_response(cb), cb, comment.author)
                self.log("Bot replying to : "+cb+"\nURL : "+cpl)
                self.log("Response : "+response+"\n------------------------------------------------")
                self.lock.release()
                cntr += 1
            cp.reply(response)
        except:
            self.log("An error occured while replying")
        return

    
    def run_mt(self, n_threads):
        self.log("Starting Run... "+str(time.time()))
        # Get the top 5 values from our subreddit
        subrs = []
        with open('/mnt/sub_list.txt', 'r') as sf:
            for line in sf:
                if line.strip(): subrs.append(line.strip())
        all_arr = [self.reddit().subreddit(subr) for subr in subrs]
        # n_threads = len(subrs)
        # def deploy_stream(self, subr):
        #     with parallel_backend('threading', n_jobs=1):
        #         Parallel()(delayed(do_work)(self, comment) for comment in subr.stream.comments(skip_existing=True))
        #
        # self.log("\nDeploying "+str(n_threads)+" threads")
        # with parallel_backend('threading', n_jobs=n_threads):
        #     Parallel()(delayed(deploy_stream)(self, subr) for subr in tqdm.tqdm(all_arr))
         
        
        ctr = 0
        for subr in all_arr:
            self.sel.register(AugComStream(subr, ctr, skip_existing=True))
            ctr += 1

        
        all_arr = [self.reddit().subreddit(subr) for subr in subrs]
        n_threads = len(all_arr)
        self.log("\nDeploying "+str(n_threads)+" threads")
        def deploy_stream(self, subr):
            with parallel_backend('threading', n_jobs=32):
                Parallel()(delayed(self.do_work)(comment) for comment in subr.stream.comments(skip_existing=True))

        with parallel_backend('threading', n_jobs=n_threads):
            Parallel()(delayed(deploy_stream)(self, subr) for subr in tqdm.tqdm(all_arr))
            
        self.log("\nMAIN THREAD DONE!!!\n\n============================================================\n")

with open("./reddit_bot_logs.txt", 'a+') as log:
    w = sys.stdout.write
    def wlog(data, flush=False, silent=False):
        data += "\n"
        if not silent:
            w(data)
        log.write(data)
        if flush:
            log.flush()
    bot = GPT2Bot(wlog)
    bot.run_loop()
