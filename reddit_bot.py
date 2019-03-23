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

m_guy = False

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
        if comment.author is None or comment.author.name == "GPT-2_Bot":
            return
        if rexp.match(clean_input(comment.body)) is None:
            return
        for h in comment.replies:
            if h.author.name == "GPT-2_Bot":
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
                    if h.author.name == "GPT-2_Bot":
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

def run_mt(lock, n_threads, log):
    def do_work(comment, lock, log, rexp):
        if not t_man:
            global t_man
            t_man = True
            lock.acquire()
            log("\n================ RUNNING SUBMISSION SWEEP ================\n\n")
            lock.release()
            run(lock, 4, log, 'b3z92d')
            run(lock, 4, log, 'b3zlha')
            run(lock, 4, log, 'b4duec')
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
            log("An unknown error occured.\n")
            return

        cb = ""
        for line in cp.body.splitlines():
            if line.strip():
                insensitive_hippo = re.compile(re.escape('**INPUT(.*):**'), re.IGNORECASE)
                insensitive_d = re.compile(re.escape("Beep boop, I'm a bot."), re.IGNORECASE)
                cb += str(insensitive_hippo.sub('', str(insensitive_d.sub('', line.strip())))) + "\n"
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
    srs = ["MachineLearning", "all"]
    subs = [reddit.subreddit(sub) for sub in srs]
    all = reddit.subreddit('all')
    submission = praw.models.Submission(reddit, id='b32lve')
    submission.comments.replace_more(limit=None)
    rexp = re.compile(r"^(.*)gpt-2(.*)finish this(.*)$", re.IGNORECASE|re.DOTALL)
    with parallel_backend('threading', n_jobs=n_threads):
        Parallel()(delayed(do_work)(comment, lock, log, rexp) for comment in tqdm.tqdm(all.stream.comments(skip_existing=True, pause_after=0)) if comment is not None)

    log("DONE!!!\n\n============================================================\n")

with open("./reddit_bot_logs.txt", 'a') as log:
    w = sys.stdout.write
    def wlog(str, flush=False, silent=False):
        str += "\n"
        if not silent:
            w(str)
        log.write(str)
        if flush:
            log.flush()
    print("START")
    g_lock = Lock()
    while True:
        try:
            run_mt(g_lock, 32, wlog)
        except KeyboardInterrupt:
            wlog("\nUser pressed ctrl-c...")
            break
        except:
            wlog("\nUnspecified error during run. Restarting...")
