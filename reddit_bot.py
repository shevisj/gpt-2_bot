#!/usr/bin/python
import sys
import praw
import re
import random
import os
import pbd
import string
import time
from joblib import Parallel, delayed, parallel_backend
from threading import Lock
import tqdm
import fire
import json
import os
import tensorflow as tf
import numpy as np

import model, sample, encoder

enc = None
g_sess = None
g_batch_size = 1
g_nsamples = 1
g_callback = print

def get_model(
    model_name='117M',
    seed=None,
    nsamples=1,
    batch_size=1,
    length=None,
    temperature=1,
    top_k=40,
):
    if batch_size is None:
        batch_size = 1
    assert nsamples % batch_size == 0
    global enc
    global g_sess
    global g_batch_size
    global g_nsamples
    enc = encoder.get_encoder(model_name)
    hparams = model.default_hparams()
    with open(os.path.join('models', model_name, 'hparams.json')) as f:
        hparams.override_from_dict(json.load(f))

    if length is None:
        length = hparams.n_ctx // 2
    elif length > hparams.n_ctx:
        raise ValueError("Can't get samples longer than window size: %s" % hparams.n_ctx)

    with tf.Session(graph=tf.Graph()) as sess:
        context = tf.placeholder(tf.int32, [batch_size, None])
        np.random.seed(seed)
        tf.set_random_seed(seed)
        output = sample.sample_sequence(
            hparams=hparams, length=length,
            context=context,
            batch_size=batch_size,
            temperature=temperature, top_k=top_k
        )

        saver = tf.train.Saver()
        ckpt = tf.train.latest_checkpoint(os.path.join('models', model_name))
        saver.restore(sess, ckpt)
        g_batch_size = batch_size
        g_nsamples = nsamples
        g_sess = sess
        g_callback()

def clean_input(s):
    return ''.join(filter(lambda x: x in set(string.printable), s))

def get_response(input_str):
    if not clean_input(input_str):
        return "Unable to read comment. Make sure there aren't any special characters."
    context_tokens = enc.encode()
    generated = 0
    sample = ""
    for _ in range(g_nsamples // g_batch_size):
        out = g_sess.run(output, feed_dict={
            context: [context_tokens for _ in range(g_batch_size)]
        })[:, len(context_tokens):]
        for i in range(g_batch_size):
            generated += 1
            text = enc.decode(out[i])
            sample += clean_output(text)
    return sample

def clean_response(resp, inp, user=None):
    resp = resp.encode('utf-8')
    resp = resp.split('<|endoftext|>'.encode('utf-8'))[0]
    sp = resp.splitlines()
    print("Split len", len(sp))
    out = ""

    ctr = 0
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
    return str(pref + iop + "\n" + out + "\nBeep boop, I'm a bot.")

m_guy = False
stream_guy = False

def run(lock, n_threads, log, subm):
    def message_guy(reddit, lock, log):
        log("MESSAGE GUY STARTING\n")
        global m_guy
        m_guy = True
        for message in reddit.inbox.unread(limit=None):
            if isinstance(message, praw.models.Message):
                log("Found a DM!\n", silent=True)
                cb = ""
                for line in message.body.splitlines():
                    if line.strip():
                        insensitive_hippo = re.compile(re.escape('**INPUT(.*):**'), re.IGNORECASE)
                        insensitive_d = re.compile(re.escape("Beep boop, I'm a bot."), re.IGNORECASE)
                        cb += str(insensitive_hippo.sub('', str(insensitive_d.sub('', line))))
                cb = clean_input(cb)

                if len(cb.strip()) < 2:
                    log("Parent comment was empty", silent=True)
                    continue

                lock.acquire()
                response = clean_response(get_response(cb), cb)
                log("Bot replying to direct message: "+cb)
                log("Response : "+response+"\n------------------------------------------------")
                lock.release()
                message.reply(response)
                message.mark_read()

    def do_work(comment, lock, log, rexp, reddit):
        if not isinstance(comment, praw.models.Comment):
            return
        if comment.author is None or comment.author.name == reddit.user.me().name:
            return
        if rexp.match(clean_input(comment.body)) is None:
            return
        for h in comment.replies:
            if h.author.name == reddit.user.me().name:
                return
        log("Found one!", silent=True)

        try:
            cp = comment.parent()

            if isinstance(cp, praw.models.Submission):
                log("Parent was a submission...\n", silent=True)
                return
            else:
                cp.refresh()
                for h in cp.replies:
                    if h.author is None:
                        continue
                    if h.author.name == reddit.user.me().name:
                        log("Already replied to this comment...\n", silent=True)
                        return
        except:
            return
        cb = ""
        for line in cp.body.splitlines():
            if line.strip():
                insensitive_hippo = re.compile(re.escape('**INPUT(.*):**'), re.IGNORECASE)
                insensitive_d = re.compile(re.escape("Beep boop, I'm a bot."), re.IGNORECASE)
                cb += str(insensitive_hippo.sub('', str(insensitive_d.sub('', line))))
        cb = clean_input(cb)
        cpl = "https://www.reddit.com" + cp.permalink

        if len(cb.strip()) < 2:
            log("Parent comment was empty", silent=True)
            return

        lock.acquire()
        response = clean_response(get_response(cb), cb, comment.author)
        log("Bot replying to : "+cb+"\nURL : "+cpl)
        log("Response : "+response+"\n------------------------------------------------")
        lock.release()
        cp.reply(response)
        return

    reddit = praw.Reddit('gptbot')
    log("Starting Submission Run... "+str(time.time()))
    submission = praw.models.Submission(reddit, id=subm)
    submission.comments.replace_more(limit=None)
    rexp = re.compile(r"^(.*)gpt-2(.*)finish this(.*)$", re.IGNORECASE|re.DOTALL)
    message_guy(reddit, lock, log)
    with parallel_backend('threading', n_jobs=n_threads):
        Parallel()(delayed(do_work)(comment, lock, log, rexp, reddit) for comment in tqdm.tqdm(submission.comments.list()) if comment is not None)
    global m_guy
    m_guy = False
    log("SUBMISSION RUN DONE!!!\n\n============================================================\n", flush=True)


lt = time.time() - 900

t_man = False

class StreamList():
    def __init__(self):
        self.stream_file = open("./src/stream_list.txt", 'r+')
        self.list = self._load()

    def __del__(self):
        self.stream_file.close()

    def _load(self):
        out = []
        for line in self.stream_file:
            out.append(line.strip())
        return out

    def append(self, data):
        self.stream_file.write(str(data)+"\n")
        self.stream_file.flush()
        self.list.append(data)

stream_list = StreamList()

def run_mt(lock, n_threads, log):
    def should_add_to_list(subm, lock ,log):
        if "gpt-2" in subm.title.lower():
            lock.acquire()
            log("\nFound a new submission about GPT-2\nURL: "+subm.permalink)
            stream_list.append(subm.id)
            lock.release()
    def do_work(comment, lock, log, rexp, reddit):
        if not t_man:
            global t_man
            t_man = True
            lock.acquire()
            log("\n================ RUNNING SUBMISSION SWEEP ================\n\n")
            lock.release()
            with parallel_backend('threading', n_jobs=4):
                Parallel()(delayed(run)(lock, 4, log, subm) for subm in tqdm.tqdm(stream_list.list))
            time.sleep(900)
            t_man = False
        elif not stream_guy:
            global stream_guy
            stream_guy = True
            lock.acquire()
            log("\n================ RUNNING SUBMISSION STREAM ================\n\n")
            lock.release()
            all = reddit.subreddit('all')
            with parallel_backend('threading', n_jobs=4):
                Parallel()(delayed(should_add_to_list)(submission, lock, log) for submission in tqdm.tqdm(all.stream.submissions(skip_existing=True)))

        if not isinstance(comment, praw.models.Comment):
            return
        if comment.author is None or comment.author.name == reddit.user.me().name:
            return
        if rexp.match(clean_input(comment.body)) is None:
            return
        for h in comment.replies:
            if h.author.name == reddit.user.me().name:
                return
        log("Found one!")

        try:
            cp = comment.parent()

            if isinstance(cp, praw.models.Submission):
                log("Parent was a submission...\n")
                return
            else:
                cp.refresh()
                for h in cp.replies:
                    if h.author is None:
                        continue
                    if h.author.name == reddit.user.me().name:
                        log("Already replied to this comment...\n")
                        return
        except:
            log("An unknown error occured.\n")
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
            log("Parent comment was empty")
            return

        lock.acquire()
        if comment.subreddit.name == "politics":
            response = clean_response(get_response(cb), cb)
        else:
            response = clean_response(get_response(cb), cb, comment.author)
        log("Bot replying to : "+cb+"\nURL : "+cpl)
        log("Response : "+response+"\n------------------------------------------------")
        lock.release()
        cp.reply(response)
        return

    reddit = praw.Reddit('gptbot')
    log("Starting Run... "+str(time.time()))
    # Get the top 5 values from our subreddit
    all = reddit.subreddit('all')
    rexp = re.compile(r"^(.*)gpt-2(.*)finish this(.*)$", re.IGNORECASE|re.DOTALL)
    with parallel_backend('threading', n_jobs=n_threads):
        Parallel()(delayed(do_work)(comment, lock, log, rexp, reddit) for comment in tqdm.tqdm(all.stream.comments(skip_existing=True)))

    log("DONE!!!\n\n============================================================\n")

with open("./reddit_bot_logs.txt", 'a+') as log:
    w = sys.stdout.write
    def wlog(data, flush=False, silent=False):
        data += "\n"
        if not silent:
            w(data)
        log.write(data)
        if flush:
            log.flush()
    print("START")
    g_lock = Lock()
    def start():
        while True:
            try:
                run_mt(g_lock, 32, wlog)
            except KeyboardInterrupt:
                wlog("\nUser pressed ctrl-c...")
                break
            #except:
            #    wlog("\nUnspecified error during run. Restarting...")
    g_callback = start
    fire.Fire(get_model)
