# ollamasearch
Ollama-based agent to search the web locally using SearXNG and Crawl4AI

If you want to run your own LLM locally on your Jetson Orin Nano Super, this repo enables you to do it. Here's how you set it up.

## Instructions

0. **Make sure that you have set up the Jetson if not done so already and that you can run ollama:**

See for example the tutorial to set up Ollama on the jetson below.
 - https://www.jetson-ai-lab.com/tutorial_ollama.html

1. **Create new conda env, pull an LLM from https://ollama.com/search and install dependencies**

```
conda create -n webagents python=3.10 -y
conda activate webagents
pip install -r requirements.txt
ollama pull llama3.2:3b
```


2. **Set-up SearchXNG with docker**

```
cd /opt
sudo git clone https://github.com/searxng/searxng-docker.git
cd searxng-docker/
```

open `searxng/settings.yml` and if not present add the following to enable the search format json API:

```
search:
  formats:
    - html
    - json
```
To generate secrets and export `SEARCH_URL`:

```
sed -i "s|ultrasecretkey|$(openssl rand -hex 32)|g" searxng/settings.yml
```

Add this line to the `~./bashrc` file and then `source ~./bashrc`

```
export SEARCH_URL="http://127.0.0.1:8080/search"
```
Then run docker compose to launch the SearXNG application on port 8080 inside Docker

```
docker compose up -d
```

Verify thaat it is running correctly:

```
curl -kLX GET --data-urlencode q='test query' \
     -G 'http://localhost:8080/search' -d format=json
```

3. **Set-up SearXNG with docker**

Run an example to check that everything is working and you should see that the ollama is searching the web.

```
run-agent-swarm -c examples/settings.yaml -o output.md
```

# Credits

Inspired by Matt Williams' video

[![Watch the video](https://img.youtube.com/vi/GMlSFIp1na0/maxresdefault.jpg)](https://www.youtube.com/watch?v=GMlSFIp1na0&t=85s)

Check also the repo for an implementation in typescript and more:

 - https://github.com/technovangelist/videoprojects
