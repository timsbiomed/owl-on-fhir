"""Convert OWL to FHIR"""
import os
import shutil
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import Dict, List, Union

import curies
import requests
from linkml_runtime.loaders import json_loader
from oaklib.converters.obo_graph_to_fhir_converter import OboGraphToFHIRConverter
from oaklib.datamodels.obograph import GraphDocument
from oaklib.interfaces.basic_ontology_interface import get_default_prefix_map
from urllib.parse import urlparse

from sssom.parsers import parse_sssom_table
from sssom.writers import write_fhir_json

# Vars
# - Vars: Static
SRC_DIR = os.path.dirname(os.path.realpath(__file__))
BIN_DIR = SRC_DIR
PROJECT_DIR = os.path.join(SRC_DIR, '..')
CACHE_DIR = os.path.join(PROJECT_DIR, 'cache')
ROBOT_PATH = os.path.join(BIN_DIR, 'robot.jar')


# Functions
def _run_shell_command(command: str, cwd_outdir: str = None) -> subprocess.CompletedProcess:
    """Runs a command in the shell, and handles some common errors"""
    args = command.split(' ')
    if cwd_outdir:
        result = subprocess.run(args, capture_output=True, text=True, cwd=cwd_outdir)
    else:
        result = subprocess.run(args, capture_output=True, text=True)
    stderr, stdout = result.stderr, result.stdout
    if stderr and 'Unable to create a system terminal, creating a dumb terminal' not in stderr:
        raise RuntimeError(stderr)
    elif stdout and 'error' in stdout or 'ERROR' in stdout:
        raise RuntimeError(stdout)
    elif stdout and 'make: Nothing to be done' in stdout:
        raise RuntimeError(stdout)
    elif stdout and ".db' is up to date" in stdout:
        raise FileExistsError(stdout)
    return result


def _preprocess_rxnorm(path: str) -> str:
    """Preprocess RXNORM
    If detects a Bioportal rxnorm TTL, makes some modifications to standardize it to work with OAK, etc.
    See: https://github.com/INCATools/ontology-access-kit/issues/427
    If using --use-cached-intermediaries or --retain-intermediaries, those are used for SemSQL or Obographs
    intermediaries, but not the intermediary created by this function.
    """
    if '-fixed' in path:
        return path
    print('INFO: RXNORM.ttl from Bioportal detected. Doing some preprocessing.')
    outpath = path.replace(".ttl", "-fixed.ttl")
    _run_shell_command(f'cp {path} {outpath}')
    command_str = f'perl -i {os.path.join(BIN_DIR, "convert_owl_ncbo2owl.pl")} {outpath}'
    _run_shell_command(command_str)
    return outpath


def download(url: str, path: str, save_to_cache=False, download_if_cached=True):
    """Download file at url to local path

    :param download_if_cached: If True and file at `path` already exists, download anyway."""
    _dir = os.path.dirname(path)
    if not os.path.exists(_dir):
        os.makedirs(_dir)
    if download_if_cached or not os.path.exists(path):
        with open(path, 'wb') as f:
            response = requests.get(url, verify=False)
            f.write(response.content)
    if save_to_cache:
        cache_path = os.path.join(CACHE_DIR, os.path.basename(path))
        shutil.copy(path, cache_path)


def owl_to_obograph(inpath: str, out_dir: str, use_cache=False, cache_output=False) -> str:
    """Convert OWL to Obograph
    todo: TTL and RDF also supported? not just OWL?"""
    # Vars
    infile = os.path.basename(inpath)
    cache_path = os.path.join(CACHE_DIR, infile + '.obographs.json')
    outpath = os.path.join(out_dir, infile + '.obographs.json')
    command = f'java -jar {ROBOT_PATH} convert -i {inpath} -o {outpath} --format json'

    # Convert
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    if use_cache and os.path.exists(cache_path):
        return cache_path
    # todo: Switch back to `bioontologies` when complete: https://github.com/biopragmatics/bioontologies/issues/9
    # from bioontologies import robot
    # parse_results: robot.ParseResults = robot.convert_to_obograph_local(inpath)
    # graph = parse_results.graph_document.graphs[0]
    _run_shell_command(command)

    if cache_output:
        shutil.copy(outpath, cache_path)

    return outpath


def obograph_to_fhir(
    inpath: str, out_dir: str, out_filename: str = None, code_system_id: str = None, code_system_url: str = None,
    include_all_predicates=True, native_uri_stems: List[str] = None, dev_oak_path: str = None,
    dev_oak_interpreter_path: str = None
) -> str:
    """Convert Obograph to FHIR"""
    out_path = os.path.join(out_dir, out_filename)
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    local_dev_exists: bool = (os.path.exists(dev_oak_path) if dev_oak_path else False) and (
        os.path.exists(dev_oak_interpreter_path) if dev_oak_interpreter_path else False)
    native_uri_stems_str = '"' + ','.join(native_uri_stems) + '"' if native_uri_stems else None
    if dev_oak_path and local_dev_exists:  # Params last updated: 2023/01/15
        dev_oak_cli_path = os.path.join(dev_oak_path, 'src', 'oaklib', 'cli.py')
        command_str = \
            f'{dev_oak_interpreter_path} {dev_oak_cli_path} -i {inpath} dump -o {out_path} -O fhirjson' + \
            ' --include-all-predicates' if include_all_predicates else '' + \
            f' --code-system-id {code_system_id}' if code_system_id else '' + \
            f' --code-system-url {code_system_url}' if code_system_url else '' + \
            f' --native-uri-stems {native_uri_stems_str}' if native_uri_stems_str else ''
        _run_shell_command(command_str)

    elif dev_oak_path and not local_dev_exists:
        print('Warning: Tried to use local dev OAK, but one of paths does not exist. Using installed OAK release.')
    else:
        converter = OboGraphToFHIRConverter()
        converter.curie_converter = curies.Converter.from_prefix_map(get_default_prefix_map())
        gd: GraphDocument = json_loader.load(str(inpath), target_class=GraphDocument)
        converter.dump(
            gd,
            out_path,
            code_system_id=code_system_id,
            code_system_url=code_system_url,
            include_all_predicates=include_all_predicates,
            native_uri_stems=native_uri_stems)
        # TODO: add these params once supported: use_curies_native_concepts, use_curies_foreign_concepts
        # converter.dump(
        #     gd, out_path, code_system_id='', code_system_url='', include_all_predicates=include_all_predicates,
        #     native_uri_stems=native_uri_stems, use_curies_native_concepts=False, use_curies_foreign_concepts=True)
    return out_path


def write_concept_maps(obograph_path: str, outdir: str = None, code_system_id: str = None, verbose=True):
    """"From an Obograph JSON, convert to SSSOM, then convert to 1+ ConceptMap JSON"""
    # Vars
    outdir = outdir or obograph_path
    outdir = outdir if os.path.isdir(outdir) else os.path.dirname(outdir)
    # todo: ascertaining code_system_id: could be more combinations like - or _ obographs
    code_system_id = code_system_id or os.path.basename(obograph_path)\
        .replace(".obographs", "").replace(".obograph", "").replace(".json", "")
    outpath_sssom = os.path.join(outdir, f"{code_system_id}.sssom.tsv")

    # TODO: create metadata.sssom.yml
    # TODO: First, try creating one manually
    metadata_path = os.path.join(outdir, 'temp-metadata.sssom.yml')

    # todo: is there a way to do this via Python API? would be better
    # todo: -m metadata.sssom.yml: can I create this file on the fly and pass?
    command_str = f'sssom parse {obograph_path} -I obographs-json -o {outpath_sssom} -m {metadata_path}'
    print('Converting: Obographs -> SSSSOM')
    result = subprocess.run(command_str.split(), capture_output=True, text=True)
    stderr, stdout = result.stderr, result.stdout
    if 'error' in stderr.lower():
        raise RuntimeError(stderr)
    if verbose:
        print(stdout)
        print(stderr, file=sys.stderr)

    # TODO: Fix bug: Bug?: Obographs parser: metadata not utilized; getting 0 mappings #456 https://github.com/mapping-commons/sssom-py/issues/456
    # todo: outpath_concept_map: temporary. in next sssom update, will be outdir cuz 2+ maps
    print('Converting: SSSOM -> ConceptMaps')
    outpath_concept_map = os.path.join(outdir, f'ConceptMap-{code_system_id}.json')
    df = parse_sssom_table(outpath_sssom)
    with open(outpath_concept_map, "w") as file:
        write_fhir_json(df, file)


def owl_to_fhir(
    input_path_or_url: Union[str, Path], out_dir: Union[str, Path] = None, out_filename: str = None,
    include_only_critical_predicates=False, retain_intermediaries=False, use_cached_intermediaries=False,
    intermediary_outdir: str = None, convert_intermediaries_only=False, native_uri_stems: List[str] = None,
    code_system_id: str = None, code_system_url: str = None, dev_oak_path: str = None,
    dev_oak_interpreter_path: str = None, rxnorm_bioportal=False, include_codesystem=True, include_conceptmap=True
) -> str:
    """Run conversion

    :param rxnorm_bioportal: Special custom case. Set True if the file being processed is RxNorm.ttl from BioPortal."""
    include_all_predicates = not include_only_critical_predicates

    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

    # Download if necessary & determine outpaths
    # todo: this section w/ urls, names, and IDs has too many possible branches and is error prone. simplify by
    #  updating CLI params to require url or path separately, and maybe require codesystem id
    input_path_or_url = str(input_path_or_url)
    input_path = input_path_or_url
    url = None
    maybe_url = urlparse(input_path_or_url)
    out_dir = str(out_dir) if out_dir else os.getcwd()
    if out_dir.startswith('~'):
        out_dir = os.path.expanduser('~/Desktop')
    if maybe_url.scheme and maybe_url.netloc:
        url = input_path_or_url
    if url:
        download_path = os.path.join(out_dir, out_filename.replace('.json', '.owl'))
        input_path = download_path
        download(url, download_path, use_cached_intermediaries)
    if not out_filename:
        if not code_system_id:
            code_system_id = '.'.join(os.path.basename(input_path).split('.')[0:-1])  # removes file extension
        out_filename = f'CodeSystem-{code_system_id}.json'
    if not code_system_id and out_filename and out_filename.startswith('CodeSystem-'):
        code_system_id = out_filename.split('-')[1].split('.')[0]
    out_dir = os.path.realpath(out_dir if out_dir else os.path.dirname(input_path))
    intermediary_outdir = intermediary_outdir if intermediary_outdir else out_dir

    # Preprocessing: Special cases
    if rxnorm_bioportal:
        input_path = _preprocess_rxnorm(input_path)

    # Convert intermediary: Obograph
    intermediary_path = owl_to_obograph(input_path, out_dir, use_cached_intermediaries, use_cached_intermediaries)
    if convert_intermediaries_only:
        return intermediary_path

    # Convert: CodeSystem
    if include_codesystem:
        obograph_to_fhir(
            inpath=intermediary_path, out_dir=intermediary_outdir, out_filename=out_filename,
            code_system_id=code_system_id, code_system_url=code_system_url, native_uri_stems=native_uri_stems,
            include_all_predicates=include_all_predicates, dev_oak_path=dev_oak_path,
            dev_oak_interpreter_path=dev_oak_interpreter_path)

    # Convert: ConceptMap
    if include_conceptmap:
        write_concept_maps(intermediary_path, out_dir, code_system_id)

    # Cleanup
    if not retain_intermediaries:
        os.remove(intermediary_path)
    return os.path.join(out_dir, out_filename)


# TODO: some of these args said"for fhirjson only". Was this because I was going to add an option for NPM output when
#  OAK supports? Either way, removed for now till I figure out if I really was parameterizing something here.
def cli():
    """Command line interface."""
    parser = ArgumentParser(prog='OWL on FHIR', description='Python-based non-minimalistic OWL to FHIR converter.')
    parser.add_argument('-i', '--input-path-or-url', required=True, help='URL or path to OWL file to convert.')
    parser.add_argument(
        '-s', '--code-system-id', required=True, default=False,
        help="The code system ID to use for identification on the server uploaded to. "
             "See: https://hl7.org/fhir/resource-definitions.html#Resource.id")
    parser.add_argument(
        '-S', '--code-system-url', required=True, default=False,
        help="Canonical URL for the code system. "
             "See: https://hl7.org/fhir/codesystem-definitions.html#CodeSystem.url")
    parser.add_argument(
        '-u', '--native-uri-stems', required=True, nargs='+',
        help='A comma-separated list of URI stems that will be used to determine whether a concept is native to '
             'the CodeSystem. For example, for OMIM, the following URI stems are native: '
             'https://omim.org/entry/,https://omim.org/phenotypicSeries/PS". '
             'As of 2023-01-15, there is still a bug in the Obographs spec and/or `robot` where certain nodes are not'
             ' being converted. This converter adds back the nodes, but to know which ones belong to the CodeSystem '
             'itself and are not foreign concepts, this parameter is necessary. OAK also makes use of this parameter. '
             'See also: https://github.com/geneontology/obographs/issues/90')
    parser.add_argument(
        '-o', '--out-dir', required=False, default=os.getcwd(),
        help='Output directory. Defaults to current working directory.')
    parser.add_argument(
        '-n', '--out-filename', required=False, help='Filename for the primary file converted, e.g. CodeSystem.')
    parser.add_argument(
        '-p', '--include-only-critical-predicates', action='store_true', required=False, default=False,
        help='If present, includes only critical predicates (is_a/parent) rather than all predicates in '
             'CodeSystem.property and CodeSystem.concept.property.')
    parser.add_argument(
        '-c', '--use-cached-intermediaries', action='store_true', required=False, default=False,
        help='Use cached intermediaries if they exist? Also will save intermediaries to owl-on-fhir\'s cache/ dir.')
    parser.add_argument(
        '-r', '--retain-intermediaries', action='store_true', default=False, required=False,
        help='Retain intermediary files created during conversion process (e.g. Obograph JSON)?')
    parser.add_argument(
        '-I', '--convert-intermediaries-only', action='store_true', default=False, required=False,
        help='Convert intermediaries only?')
    parser.add_argument(
        '-d', '--dev-oak-path', default=False, required=False,
        help='If you want to use a local development version of OAK, specify the path to the OAK directory here. '
             'Must be used with --dev-oak-interpreter-path.')
    parser.add_argument(
        '-D', '--dev-oak-interpreter-path', default=False, required=False,
        help='If you want to use a local development version of OAK, specify the path to the Python interpreter where '
             'its dependencies are installed (i.e. its virtual environment). Must be used with --dev-oak-path.')

    d: Dict = vars(parser.parse_args())
    owl_to_fhir(**d)


# Execution
if __name__ == '__main__':
    cli()
