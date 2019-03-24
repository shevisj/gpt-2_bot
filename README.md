# gpt-2_bot
This is a reddit bot based on OpenAi's GPT-2 117M model

## Installation
### Requirements
 - Docker
 - An internet connection
 - Some pretty beefy hardware

### Installing Docker

 - [Mac](https://docs.docker.com/docker-for-mac/install)
 - [Windows](https://docs.docker.com/docker-for-windows/install)
 - [Ubuntu](https://docs.docker.com/install/linux/docker-ce/ubuntu/)

 Docker command-line interface reference:
 https://docs.docker.com/engine/reference/commandline/cli/

### Installing Latest Tensorflow Docker Image

[Follow instructions here (scroll down for GPU)](https://www.tensorflow.org/install/source#docker_linux_builds)

Perform all remaining steps from within this docker container.

### Installing GPT-2
To run this bot, you must first clone the original GPT-2 repository.

```
git clone https://github.com/openai/gpt-2.git
cd gpt-2
```

Once this is done, install the python requirements and download the model.

```
pip install --upgrade pip
pip install -r requirements.txt
python download_model.py 117M
```

Once this has completed successfully, you can test it by running:

```
python ./src/interactive_conditional_samples.py
```

### Installing Reddit Bot
Next, if you haven't already, back out of the gpt-2 directory and clone the gpt-2_bot repository:

```
cd ..
git clone https://github.com/shevisjohnson/gpt-2_bot.git
cd gpt-2_bot
```

Next, install requirements:

```
pip install -r requirements.txt
```

And finally, copy `reddit_bot.py` over to the main GPT-2 repository:

```
cp ./reddit_bot.py ../gpt-2/reddit_bot.py
```

### Configuring Praw (Reddit python interface)
Praw is a library that interfaces with the Reddit API for you. It limits how many requests you can make, and makes it easy to extract the json responses.

You need to do a bit of setup first though in order for the bot to be able to post to Reddit.

Go to: https://www.reddit.com/prefs/apps/

And select Create App

Give it a name. You have to choose a redirect uri (for some stupid reason, stupid because I'm building a bot, not a webapp, but whatever). I chose http://127.0.0.1

You will now get a client_id (red box below) and secret (blue box below). Note it down, but keep it secret.

<img src="https://www.pythonforengineers.com/wp-content/uploads/2014/11/redditbot2.jpg" alt="" width="600" height="300">

[credit](https://www.pythonforengineers.com/build-a-reddit-bot-part-1/)


Now, you need to update your praw ini file to remember these settings. Otherwise, you’ll have to put them in your script and thats dangerous (as others might see them).

This page describes how to change praw.ini files: https://praw.readthedocs.io/en/v4.0.0/getting_started/configuration/prawini.html

_I don’t recommend modifying the package-level praw.ini as those changes will be overwritten every time the package is updated. Instead praw.ini should be placed in the directory that the program is run from (often the same directory as the file)._

In your praw.ini file, make sure the profile tag is set to `gptbot`

## Running the bot
Once setup is complete, actually running the bot is very simple.
```
python reddit_bot.py
```
That's it!


Big thanks to [OpenAI](https://github.com/openai) for releasing this model publicly!
