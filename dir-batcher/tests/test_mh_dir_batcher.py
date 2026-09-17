# Synthetic unit tests for mh.asset.dir-batcher_1.0, per MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md
# section 5.
#
# Every fixture is built by the test. Nothing here reads a real tree, a real repo, a dispatcher or a
# params file - which is why every expected value below could be written down in advance.
#
# Run:  pytest dir-batcher/tests

from mh_dir_batcher import (scan, is_selected, chunk, rec_key, type_name, to_records, is_synthetic, describe, is_localized,
                            MASKS_JAVA, MASKS_ANGULAR, ALL_FILE_MASKS)


def paths(count):
    return ['/f/%03d' % i for i in range(count)]


def write(root, *parts):
    target = root.joinpath(*parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('x')
    return str(target)


# ----------------------------------------------------------------- the positive filter

def test_masks_select_source_files():
    for name in ['Foo.java', 'notes.md', 'schema.sql', 'app.ts', 'app.js', 'main.go', 'setup.py',
                 'page.html', 'a.css', 'b.scss', 'c.sass', 'app.properties']:
        assert is_selected(name), name + ' must be selected'


def test_masks_select_build_and_project_files_by_exact_name():
    for name in ['pom.xml', 'build.xml', 'angular.json', 'package.json']:
        assert is_selected(name), name + ' must be selected'


def test_masks_select_license_with_any_extension():
    assert is_selected('LICENSE.txt')
    assert is_selected('LICENSE.md')


def test_masks_reject_everything_else():
    for name in ['photo.png', 'archive.zip', 'Foo.class', 'notes.txt', 'data.csv', 'other.xml']:
        assert not is_selected(name), name + ' must not be selected'


def test_masks_are_case_sensitive_on_every_platform():
    # fnmatchcase, so a Linux Processor and a Windows Processor batch the same tree identically
    assert is_selected('Foo.java')
    assert not is_selected('Foo.JAVA')


def test_mask_groups_compose_into_the_full_set():
    for mask in MASKS_JAVA + MASKS_ANGULAR:
        assert mask in ALL_FILE_MASKS, mask + ' must reach the full set'


# ----------------------------------------------------------------- the negative filter, applied first

def test_scan_prunes_well_known_build_and_dependency_dirs(tmp_path):
    keep = write(tmp_path, 'src', 'Kept.java')
    for excluded in ['target', 'build', 'out', 'dist', 'node_modules', 'bin', 'vendor', 'coverage']:
        write(tmp_path, excluded, 'Generated.java')

    assert scan(str(tmp_path)) == [keep]


def test_scan_prunes_dot_dirs_including_git_and_angular(tmp_path):
    keep = write(tmp_path, 'Kept.java')
    write(tmp_path, '.git', 'HEAD.md')
    write(tmp_path, '.angular', 'cache.json')
    write(tmp_path, '.idea', 'workspace.md')

    assert scan(str(tmp_path)) == [keep]


def test_negative_filter_wins_over_a_matching_mask(tmp_path):
    # THE precedence assertion: a .java under node_modules matches the mask on its name alone, and
    # must still be excluded, because the tree it sits in is what makes it generated or vendored
    keep = write(tmp_path, 'src', 'Kept.java')
    write(tmp_path, 'node_modules', 'some-lib', 'Vendored.java')
    write(tmp_path, 'target', 'generated-sources', 'Generated.java')

    assert scan(str(tmp_path)) == [keep]


def test_scan_finds_selected_files_sorted_and_drops_the_rest(tmp_path):
    b = write(tmp_path, 'b.java')
    a = write(tmp_path, 'a.java')
    c = write(tmp_path, 'sub', 'c.md')
    write(tmp_path, 'ignored.txt')
    write(tmp_path, 'sub', 'ignored.png')

    assert scan(str(tmp_path)) == sorted([a, b, c])


def test_scan_walks_the_root_even_when_the_root_is_a_dot_dir(tmp_path):
    root = tmp_path / '.hidden-root'
    root.mkdir()
    kept = write(root, 'a.java')

    assert scan(str(root)) == [kept]


def test_scan_empty_dir_is_empty_list(tmp_path):
    assert scan(str(tmp_path)) == []


# ----------------------------------------------------------------- batching

def test_chunk_cuts_at_the_batch_size():
    assert [len(c) for c in chunk(paths(250), 100)] == [100, 100, 50]


def test_chunk_loses_nothing_and_keeps_order():
    original = paths(250)
    assert [p for c in chunk(original, 100) for p in c] == original


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
    assert type_name(42) == 'mh.asset.dir-batch-for-requirements.42'
    assert type_name(43) != type_name(42), 'two runs must not share a table'


def test_type_name_accepts_an_alternative_prefix():
    assert type_name(42, 'other.prefix') == 'other.prefix.42'


def test_to_records_body_is_one_path_per_line():
    records = to_records('mh.asset.dir-batch-for-requirements.42', paths(250), 100)

    assert len(records) == 3
    assert records[0]['type'] == 'mh.asset.dir-batch-for-requirements.42'
    assert records[0]['recKey'] == 'batch-0001'
    assert len(records[0]['body'].split('\n')) == 100
    assert len(records[2]['body'].split('\n')) == 50
    assert records[0]['body'].split('\n')[0] == '/f/000'


def test_to_records_empty_dir_produces_no_records():
    assert to_records('mh.asset.dir-batch-for-requirements.42', [], 100) == []

# ----------------------------------------------------------------- the production switch

def test_production_mode_is_the_literal_true_and_nothing_else():
    assert is_synthetic('true') is False


def test_everything_other_than_true_means_development():
    for value in ['mh.null-value', '', '  ', 'false', 'True', 'TRUE', 'yes', '1', 'production', None]:
        assert is_synthetic(value) is True, repr(value) + ' must not select the production store'


def test_production_value_is_stripped_before_it_is_judged():
    assert is_synthetic('  true  ') is False

# ----------------------------------------------------------------- the registry descriptor

def test_describe_names_the_tree_that_was_scanned():
    d = describe('C:/sandbox/github/derby', 4990, 100)

    assert 'C:/sandbox/github/derby' in d, 'a descriptor that omits the directory describes nothing'
    assert '4990' in d
    assert '100' in d


def test_describe_survives_an_empty_tree():
    assert '0 files' in describe('/tmp/empty', 0, 100)

# ----------------------------------------------------------------- F1 and F2, the 2026-09-16 correction

def test_f1_classes_is_excluded_like_any_other_build_output(tmp_path):
    keep = write(tmp_path, 'java', 'Kept.java')
    write(tmp_path, 'classes', 'engine', 'org', 'apache', 'derby', 'loc', 'm0_en.properties')
    write(tmp_path, 'classes', 'Generated.java')

    assert scan(str(tmp_path)) == [keep], 'a corpus names its output dir what it likes; only the tree tells'


def test_f2_localized_bundles_are_not_selected():
    for name in ['clientmessages_ru.properties', 'messages_zh_TW.properties',
                 'servlet_ja_JP.properties', 'clientmessages_qq_PP_testOnly.properties']:
        assert is_localized(name), name + ' restates a contract in another language'
        assert not is_selected(name), name + ' must not reach the queue'


def test_f2_english_and_plain_properties_survive():
    for name in ['messages.properties', 'application.properties', 'metadata.properties',
                 'info.properties', 'clientmessages_en.properties']:
        assert not is_localized(name), name + ' is not a restatement'
        assert is_selected(name), name + ' is the contract, not a translation of it'


def test_f2_applies_only_to_properties():
    assert not is_localized('Messages_ru.java')
    assert is_selected('Messages_ru.java'), 'the rule is about message bundles, not about every file'
