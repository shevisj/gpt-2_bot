#!/usr/bin/python
import sys
import praw
import re
import random
import os
import pbd
import pexpect
import string
import time
from joblib import Parallel, delayed, parallel_backend
from threading import Lock
import tqdm

def clean_input(s):
    return ''.join(filter(lambda x: x in set(string.printable), s))

def get_response(input_str):

    sample = str("\n======================================== SAMPLE 1 ========================================  I'm having some trouble understanding you. Make sure you don't have any sepcial characters in your prompt.").encode('utf-8')

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

def clean_response(resp, inp, user=None):
    resp = str(resp[92:]).encode('utf-8')
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

def run(lock, n_threads, log):
    def do_work(comment, lock, log, rexp):
        if not isinstance(comment, praw.models.Comment):
            return
        if comment.author is None or comment.author.name == "GPT-2_Bot":
            return
        if rexp.match(clean_input(comment.body)) is None:
            return
        for h in comment.replies:
            if h.author.name == "GPT-2_Bot":
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
                    if h.author.name == "GPT-2_Bot":
                        log("Already replied to this comment...\n")
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
        cpl = "https://www.reddit.com" + comment.permalink

        lock.acquire()
        log("Bot replying to : "+cb+"\nURL : "+cpl)
        response = clean_response(get_response(cb), cb, comment.author)
        log("Response : "+response+"\n------------------------------------------------")
        lock.release()
        cp.reply(response)
        return

    reddit = praw.Reddit('gptbot')
    log("Starting Run... "+str(time.time()))
    submission = praw.models.Submission(reddit, id='b3zlha')
    submission.comments.replace_more(limit=None)
    rexp = re.compile(r"^(.*)gpt-2(.*)finish this(.*)$", re.IGNORECASE|re.DOTALL)
    with parallel_backend('threading', n_jobs=n_threads):
        Parallel()(delayed(do_work)(comment, lock, log, rexp) for comment in tqdm.tqdm(submission.comments.list()) if comment is not None)

    log("DONE!!!\n\n============================================================\n")


lt = time.time() - 900

t_man = False

def run_mt(lock, n_threads, log):
    def do_work(comment, lock, log, rexp):
        if not t_man:
            global t_man
            t_man = True
            lock.acquire()
            log("\n================ RUNNING SUBMISSION SWEEP ================\n\n")
            lock.release()
            run(lock, 32, log)
            time.sleep(900)
            t_man = False
        if not isinstance(comment, praw.models.Comment):
            return
        if comment.author is None or comment.author.name == "GPT-2_Bot":
            return
        if rexp.match(clean_input(comment.body)) is None:
            return
        for h in comment.replies:
            if h.author.name == "GPT-2_Bot":
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
                    if h.author.name == "GPT-2_Bot":
                        log("Already replied to this comment...\n")
                        return
        except:
            return

        cb = ""
        for line in cp.body.splitlines():
            if line.strip():
                insensitive_hippo = re.compile(re.escape('**INPUT(.*):**'), re.IGNORECASE)
                insensitive_d = re.compile(re.escape("Beep boop, I'm a bot."), re.IGNORECASE)
                cb += str(insensitive_hippo.sub('', str(insensitive_d.sub('', line.strip())))) + "\n"
        cb = clean_input(cb)
        cpl = "https://www.reddit.com" + comment.permalink

        lock.acquire()
        log("Bot replying to : "+cb+"\nURL : "+cpl)
        response = clean_response(get_response(cb), cb, comment.author)
        log("Response : "+response+"\n------------------------------------------------")
        lock.release()
        cp.reply(response)
        return

    reddit = praw.Reddit('gptbot')
    log("Starting Run... "+str(time.time()))
    # Get the top 5 values from our subreddit
    srs = ["MachineLearning", "all"]
    subs = [reddit.subreddit(sub) for sub in srs]
    all = reddit.subreddit('all')
    submission = praw.models.Submission(reddit, id='b32lve')
    submission.comments.replace_more(limit=None)
    rexp = re.compile(r"^(.*)gpt-2(.*)finish this(.*)$", re.IGNORECASE|re.DOTALL)
    with parallel_backend('threading', n_jobs=n_threads):
        Parallel()(delayed(do_work)(comment, lock, log, rexp) for comment in tqdm.tqdm(all.stream.comments(skip_existing=False, pause_after=0)) if comment is not None)

    log("DONE!!!\n\n============================================================\n")

with open("./reddit_bot_logs.txt", 'a') as log:
    w = sys.stdout.write
    def wlog(str):
        str += "\n"
        w(str)
        log.write(str)
    print("START")
    g_lock = Lock()
    try:
        run_mt(g_lock, 32, wlog)
    except KeyboardInterrupt:
        wlog("\nUser pressed ctrl-c...")
