# Synthetic unit tests for mh.asset.dir-batcher_1.0, per MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md section 5.
#
# Every fixture is built by the test. Nothing here reads a real tree, a real repo, a dispatcher or
# a params file - which is why every expected value below could be written down in advance.
#
# Run:  pytest dir-batcher/tests

from mh_dir_batcher import scan, chunk, rec_key, type_name, to_records


def paths(count):
    return ['/f/%03d' % i for i in range(count)]


def test_chunk_cuts_at_the_batch_size():
    chunks = chunk(paths(250), 100)

    assert [len(c) for c in chunks] == [100, 100, 50]


def test_chunk_loses_nothing_and_keeps_order():
    original = paths(250)

    flattened = [p for c in chunk(original, 100) for p in c]

    assert flattened == original


def test_chunk_empty_input_is_no_batches():
    assert chunk([], 100) == []


def test_chunk_fewer_files_than_the_batch_size_is_one_batch():
    assert chunk(paths(3), 100) == [['/f/000', '/f/001', '/f/002']]


def test_chunk_rejects_a_batch_size_below_one():
    try:
        chunk(paths(3), 0)
        assert False, 'a batch size of 0 must not be accepted'
    except ValueError:
        pass


def test_rec_key_is_one_based_and_padded_to_four():
    assert rec_key(1, 3) == 'batch-0001'
    assert rec_key(3, 3) == 'batch-0003'


def test_rec_key_widens_past_four_digits_so_keys_stay_sorted():
    assert rec_key(1, 12000) == 'batch-00001'
    assert rec_key(9999, 12000) < rec_key(10000, 12000)


def test_type_name_is_minted_per_run():
    assert type_name(42) == 'mh.asset.dir-batch.42'
    assert type_name(43) != type_name(42), 'two runs must not share a table'


def test_type_name_accepts_an_alternative_prefix():
    assert type_name(42, 'other.prefix') == 'other.prefix.42'


def test_to_records_body_is_one_path_per_line():
    records = to_records('mh.asset.dir-batch.42', paths(250), 100)

    assert len(records) == 3
    assert records[0]['type'] == 'mh.asset.dir-batch.42'
    assert records[0]['recKey'] == 'batch-0001'
    assert len(records[0]['body'].split('\n')) == 100
    assert len(records[2]['body'].split('\n')) == 50
    assert records[0]['body'].split('\n')[0] == '/f/000'


def test_to_records_empty_dir_produces_no_records():
    assert to_records('mh.asset.dir-batch.42', [], 100) == []


def test_scan_finds_every_regular_file_sorted(tmp_path):
    (tmp_path / 'b.txt').write_text('b')
    (tmp_path / 'a.txt').write_text('a')
    sub = tmp_path / 'sub'
    sub.mkdir()
    (sub / 'c.txt').write_text('c')

    assert scan(str(tmp_path)) == [str(tmp_path / 'a.txt'), str(tmp_path / 'b.txt'), str(sub / 'c.txt')]


def test_scan_skips_dot_dirs_by_default(tmp_path):
    (tmp_path / 'a.txt').write_text('a')
    git = tmp_path / '.git'
    git.mkdir()
    (git / 'HEAD').write_text('ref: refs/heads/master')

    assert scan(str(tmp_path)) == [str(tmp_path / 'a.txt')]


def test_scan_includes_dot_dirs_when_asked(tmp_path):
    (tmp_path / 'a.txt').write_text('a')
    git = tmp_path / '.git'
    git.mkdir()
    (git / 'HEAD').write_text('ref: refs/heads/master')

    assert scan(str(tmp_path), skip_dot_dirs=False) == [str(git / 'HEAD'), str(tmp_path / 'a.txt')]


def test_scan_walks_the_root_even_when_the_root_is_a_dot_dir(tmp_path):
    root = tmp_path / '.hidden-root'
    root.mkdir()
    (root / 'a.txt').write_text('a')

    assert scan(str(root)) == [str(root / 'a.txt')]


def test_scan_empty_dir_is_empty_list(tmp_path):
    assert scan(str(tmp_path)) == []