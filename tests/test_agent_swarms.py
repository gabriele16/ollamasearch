import pytest
from ollamasearch import AgentSwarm, SwarmConfig, load_config


@pytest.fixture
def dummy_config(tmp_path):
    cfg_file = tmp_path / "settings.yaml"
    cfg_file.write_text(
        """
        search_url: https://example.com/search
        model_name: test-model:latest
        max_urls: 1
        max_iterations: 1
        query: test
        """
    )
    return cfg_file

def test_load_config(dummy_config):
    cfg = load_config(str(dummy_config))
    assert cfg.search_url == "https://example.com/search"
    assert cfg.model_name == "test-model:latest"
    assert cfg.max_urls == 1
    assert cfg.max_iterations == 1
    assert cfg.query == "test"

class DummyAgent(AgentSwarm):
    def get_news_urls(self, query):
        return ["https://example.com/article"]
    def get_cleaned_text(self, urls):
        return ["**Source:** url\n\ncontent"]
    def answer_query(self, query, texts):
        return "Answer"
    def check_answer(self, query, answer):
        return True

def test_run_swarm_happy_path(dummy_config):
    cfg = load_config(str(dummy_config))
    agent = DummyAgent(cfg)
    result = agent.run(cfg.query)
    assert result == "Answer"

class DummyAgentLoop(AgentSwarm):
    def __init__(self, config):
        super().__init__(config)
        self.calls = 0
    def get_news_urls(self, query):
        return ["url"]
    def get_cleaned_text(self, urls):
        return ["text"]
    def answer_query(self, query, texts):
        self.calls += 1
        return "Answer" + str(self.calls)
    def check_answer(self, query, answer):
        return self.calls >= 2
    def simplify_results(self, query, texts):
        return ["simplified"]

def test_run_swarm_loop(dummy_config):
    cfg = load_config(str(dummy_config))
    cfg.max_iterations = 2
    agent = DummyAgentLoop(cfg)
    result = agent.run(cfg.query)
    assert result == "Answer2"
