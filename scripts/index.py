#!/usr/bin/env python3
import fnmatch
import json
import os
import shutil

from typing import List

THIS_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT_DIR = os.path.realpath(os.path.join(THIS_DIR, ".."))


# Source data will be taken from this directory (relative to the project root)
# Committed to repository. Modify files there.
DATA_INPUT_DIR = os.path.realpath(os.path.join(PROJECT_ROOT_DIR, "data"))

# Final, uncompressed datasets will be generated in this directory (relative to the project root)
# It is gitignored and is safe to delete. Do not modify manually.
DATA_OUTPUT_DIR = os.path.realpath(os.path.join(PROJECT_ROOT_DIR, "data_output"))

SETTINGS_JSON_PATH = os.path.realpath(os.path.join(DATA_INPUT_DIR, "settings.json"))
INDEX_JSON_PATH = os.path.realpath(os.path.join(DATA_OUTPUT_DIR, "index.json"))

from collections import namedtuple


def dict_to_namedtuple(name, dic):
    return namedtuple(name, dic.keys())(*dic.values())


def find_files(pattern, here):
    for path, dirs, files in os.walk(os.path.abspath(here)):
        for filename in fnmatch.filter(files, pattern):
            yield os.path.join(path, filename)


def find_dirs(here):
    for path, dirs, _ in os.walk(os.path.abspath(here)):
        for dirr in dirs:
            yield os.path.join(path, dirr)


def find_dirs_here(here):
    return filter(os.path.isdir, [os.path.join(here, e) for e in os.listdir(here)])


def json_write(obj, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")


def get_paths(dataset_json, version):
    dataset_name = dataset_json["name"]
    version_datetime = version["datetime"]
    versions_dir = f"{dataset_name}/versions"
    files_dir = f"{versions_dir}/{version_datetime}/files"
    files = {f"{filetype}": f"/{files_dir}/{filename}" for
             filetype, filename in version['files'].items()}

    input_files_dir_abs = os.path.realpath(os.path.join(DATA_INPUT_DIR, files_dir))
    output_files_dir_abs = os.path.realpath(os.path.join(DATA_OUTPUT_DIR, files_dir))

    zip_dir = f"{versions_dir}/{version_datetime}/zip-bundle"
    zip_base = f"nextclade_dataset_{dataset_name}_{version_datetime}"
    zip_filename = f"{zip_base}.zip"
    zip_bundle_url = f"/{zip_dir}/{zip_filename}"

    zip_base_path = os.path.join(DATA_OUTPUT_DIR, zip_dir, zip_base)
    zip_src_dir = os.path.realpath(os.path.join(DATA_OUTPUT_DIR, files_dir))

    return dict_to_namedtuple("paths", {
        "files": files,
        "versions_dir": versions_dir,
        "input_files_dir_abs": input_files_dir_abs,
        "output_files_dir_abs": output_files_dir_abs,
        "zip_base_path": zip_base_path,
        "zip_src_dir": zip_src_dir,
        "zip_bundle_url": zip_bundle_url
    })


def copy_dataset_version_files(version, src_dir, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    for _, filename in version['files'].items():
        input_filepath = os.path.join(src_dir, filename)
        output_filepath = os.path.join(dst_dir, filename)
        shutil.copy2(input_filepath, output_filepath)


def make_zip_bundle(dataset_json, version):
    paths = get_paths(dataset_json, version)
    os.makedirs(os.path.dirname(paths.zip_base_path), exist_ok=True)
    shutil.make_archive(
        base_name=paths.zip_base_path,
        format='zip',
        root_dir=paths.zip_src_dir
    )


if __name__ == '__main__':
    shutil.rmtree(DATA_OUTPUT_DIR, ignore_errors=True)

    with open(SETTINGS_JSON_PATH, 'r') as f:
        settings_json = json.load(f)

    settings = settings_json
    defaultDatasetName = settings['defaultDatasetName']
    defaultDatasetNameFriendly = None

    datasets = []
    for dataset_json_path in find_files(pattern="dataset.json", here=DATA_INPUT_DIR):
        with open(dataset_json_path, 'r') as f:
            dataset_json: dict = json.load(f)
        dataset_json_original = dataset_json.copy()

        dataset_name = dataset_json["name"]
        if dataset_name == defaultDatasetName:
            defaultDatasetNameFriendly = dataset_json['nameFriendly']

        # Read data descriptions for the tags
        dir = os.path.dirname(dataset_json_path)
        versions: List[dict] = []
        for meta_path in find_files("metadata.json", dir):
            with open(meta_path, 'r') as f:
                version_json: dict = json.load(f)

            versions.append(version_json)
        versions.sort(key=lambda x: x["datetime"], reverse=True)

        for i, version in enumerate(versions):
            tag = version["datetime"]
            paths = get_paths(dataset_json, version)

            # Generate `tag.json` inside output directory
            tag_json = {**version_json, **dataset_json}
            tag_json_path = os.path.join(paths.output_files_dir_abs, "tag.json")
            json_write(tag_json, tag_json_path)

            # Copy files, including `tag.json` into output directory
            copy_dataset_version_files(version, src_dir=paths.input_files_dir_abs, dst_dir=paths.output_files_dir_abs)

            # Zip output directory
            make_zip_bundle(dataset_json, version)

            # Copy latest version output directory to directory `latest`
            # (assumes `versions` are sorted by tag, reversed!)
            if i == 0:
                this_version_dir = os.path.join(DATA_OUTPUT_DIR, paths.versions_dir, tag)
                latest_version_dir = os.path.join(DATA_OUTPUT_DIR, paths.versions_dir, "latest")
                shutil.copytree(this_version_dir, latest_version_dir)

            version.update({"files": paths.files, "zipBundle": paths.zip_bundle_url, "latest": i == 0})

        dataset = {**dataset_json, "versions": versions}
        datasets.append(dataset)

    settings.update({'defaultDatasetNameFriendly': defaultDatasetNameFriendly})

    datasets_json = dict()
    datasets_json.update({"settings": settings})
    datasets_json.update({"datasets": datasets})
    json_write(datasets_json, INDEX_JSON_PATH)
