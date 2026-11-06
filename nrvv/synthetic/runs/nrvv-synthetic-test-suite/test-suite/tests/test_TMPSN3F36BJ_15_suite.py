import nrvv_sample


def test_greeting_returns_exact_string():
    instance = nrvv_sample.NrvvSample()
    assert instance.greeting() == 'Hello, NRVV'


def test_greeting_returns_str_type():
    instance = nrvv_sample.NrvvSample()
    result = instance.greeting()
    assert isinstance(result, str)
    assert result == 'Hello, NRVV'


def test_greeting_writes_nothing_to_stdout(capsys):
    instance = nrvv_sample.NrvvSample()
    instance.greeting()
    captured = capsys.readouterr()
    assert captured.out == ''


def test_greeting_returns_value_and_stdout_empty(capsys):
    instance = nrvv_sample.NrvvSample()
    result = instance.greeting()
    captured = capsys.readouterr()
    assert result == 'Hello, NRVV'
    assert captured.out == ''
