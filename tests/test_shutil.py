"""
Tests to validate iripau.shutil module
"""

import os
import pytest
import shutil
import tempfile

from iripau.shutil import FileLock
from iripau.shutil import create_file
from iripau.shutil import read_file
from iripau.shutil import remove_file
from iripau.shutil import remove_tree
from iripau.shutil import file_created
from iripau.shutil import rotate


class TestFileLock:

    @classmethod
    def setup_class(cls):
        cls.file_name = "a_file.lock"

    def teardown_method(self):
        try:
            os.remove(self.file_name)
        except FileNotFoundError:
            pass

    def test_interfering(self):
        lock_1 = FileLock(self.file_name)
        lock_2 = FileLock(self.file_name)

        assert not lock_1.acquired
        assert not lock_2.acquired

        lock_1.acquire()
        assert lock_1.acquired
        assert not lock_2.acquired

        with pytest.raises(TimeoutError):
            lock_2.acquire(timeout=2)

        assert lock_1.acquired
        assert not lock_2.acquired

        lock_1.release()
        assert not lock_1.acquired
        assert not lock_2.acquired

        lock_2.acquire()
        assert not lock_1.acquired
        assert lock_2.acquired

        lock_2.release()
        assert not lock_1.acquired
        assert not lock_2.acquired

    def test_context(self):
        with FileLock(self.file_name):
            assert os.path.exists(self.file_name)
        assert not os.path.exists(self.file_name)


class TestShutil:

    def setup_method(self):
        self.workspace = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.workspace)

    def path(self, *paths):
        return os.path.join(self.workspace, *paths)

    def create_tree(self, *paths_contents):
        for path, content in paths_contents:
            path = self.path(path)
            dir_name, file_name = os.path.split(path)
            os.makedirs(dir_name, exist_ok=True)
            if file_name:
                create_file(path, content)

    def assert_tree(self, root, *paths_contents):
        for path, content in paths_contents:
            path = self.path(path)
            dir_name, file_name = os.path.split(path)
            if file_name:
                assert content == read_file(path)
            else:
                assert os.path.isdir(dir_name)

    @pytest.mark.parametrize("content", ["text", b"bytes"])
    def test_file_manipulation(self, content):
        file_name = self.path("a_file.tmp")
        create_file(file_name, content=content)
        assert content == read_file(file_name, bytes == type(content))
        remove_file(file_name)
        with pytest.raises(FileNotFoundError):
            os.remove(file_name)

    def test_remove_file_not_found(self):
        file_name = self.path("a_file.tmp")
        remove_file(file_name)

    def test_remove_tree_dir(self):
        self.create_tree(
            ("dir_1/dir_2/a_file.tmp", "this is a test!")
        )
        root = self.path("dir_1")
        remove_tree(root)
        assert not os.path.exists(root)

    def test_remove_tree_file(self):
        file_name = self.path("a_file.tmp")
        create_file(file_name)
        remove_tree(file_name)
        assert not os.path.exists(file_name)

    def test_remove_tree_dir_symlink(self):
        self.create_tree(
            ("dir_1/dir_2/a_file.tmp", "this is a test!")
        )
        root = self.path("dir_1")
        link = self.path("dir_link")
        os.symlink(root, link, target_is_directory=True)
        remove_tree(link)
        assert not os.path.exists(link)
        assert os.path.exists(root)

    def test_remove_tree_file_symlink(self):
        file_name = self.path("a_file.tmp")
        create_file(file_name)
        link = self.path("file_link")
        os.symlink(file_name, link)
        remove_tree(link)
        assert not os.path.exists(link)
        assert os.path.exists(file_name)

    def test_remove_tree_not_found(self):
        root = self.path("a_directory")
        remove_tree(root)

    def test_file_created(self):
        file_name = self.path("a_file.tmp")
        with file_created(file_name, content=file_name):
            assert file_name == read_file(file_name)
        with pytest.raises(FileNotFoundError):
            os.remove(file_name)

    def test_rotate(self, tmpdir):
        self.create_tree(
            ("dir_1/a_file.tmp", ""),
            ("dir_2/other_file_3.tmp", ""),
            ("dir_2.1/other_file_2.tmp", ""),
            ("dir_2.2/other_file_1.tmp", ""),
            ("dir_3/another_file.tmp", "EEE"),
            ("dir_3/another_file.1.tmp", "DDD"),
            ("dir_3/another_file.2.tmp", "CCC"),
            ("dir_3/another_file.4.tmp", "AAA")
        )

        rotate(self.path("dir_1"))
        rotate(self.path("dir_2"))
        rotate(self.path("dir_3/another_file.tmp"))

        self.assert_tree(
            ("dir_1.1/a_file.tmp", ""),
            ("dir_2.1/other_file_3.tmp", ""),
            ("dir_2.2/other_file_2.tmp", ""),
            ("dir_2.3/other_file_1.tmp", ""),
            ("dir_3/another_file.1.tmp", "EEE"),
            ("dir_3/another_file.2.tmp", "DDD"),
            ("dir_3/another_file.3.tmp", "CCC"),
            ("dir_3/another_file.4.tmp", "AAA")
        )
        assert not os.path.exists(self.path("dir_1"))
        assert not os.path.exists(self.path("dir_2"))
        assert not os.path.exists(self.path("dir_3/another_file.tmp"))
