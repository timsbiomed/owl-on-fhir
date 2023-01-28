"""Convert OWL to FHIR"""
import json
import os
import subprocess
from argparse import ArgumentParser
from collections import OrderedDict
from typing import Dict, List

import curies
import requests
from linkml_runtime.loaders import json_loader
from oaklib.converters.obo_graph_to_fhir_converter import OboGraphToFHIRConverter
from oaklib.datamodels.obograph import GraphDocument
from oaklib.interfaces.basic_ontology_interface import get_default_prefix_map
from urllib.parse import urlparse


# Vars
# - Vars: Static
BIN_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_DIR = os.path.join(BIN_DIR, '..')
CACHE_DIR = os.path.join(PROJECT_DIR, 'cache')
OUTDIR = os.path.join(PROJECT_DIR, 'output')
ROBOT_PATH = os.path.join(BIN_DIR, 'robot')
INTERMEDIARY_TYPES = ['obographs', 'semsql']

# - Vars: Config
# TODO: owl-on-fhir-content needs some configuration / setup instructions, or a git submodule
OWL_ON_FHIR_CONTENT_REPO_PATH = os.path.join(PROJECT_DIR, '..', 'owl-on-fhir-content')
# todo: consider 1+ changes: (i) external config JSON / env vars, (ii) accept overrides from CLI
FAVORITE_DEFAULTS = {
    'out_dir': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'output'),
    'intermediary_outdir': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'input'),
    'include_all_predicates': True,
    'intermediary_type': 'obographs',
    'use_cached_intermediaries': True,
    'retain_intermediaries': True,
    'convert_intermediaries_only': False,
}
FAVORITE_ONTOLOGIES = OrderedDict({
    'mondo': {
        'download_url': 'https://github.com/monarch-initiative/mondo/releases/latest/download/mondo.owl',
        'code_system_url': 'http://purl.obolibrary.org/obo/mondo.owl',
        'input_path': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'input', 'mondo.owl'),
        'code_system_id': 'mondo',
        'native_uri_stems': ['http://purl.obolibrary.org/obo/MONDO_'],
    },
    'comp-loinc': {
        'download_url': 'https://github.com/loinc/comp-loinc/releases/latest/download/merged_reasoned_loinc.owl',
        'code_system_url': 'https://github.com/loinc/comp-loinc/releases/latest/download/merged_reasoned_loinc.owl',
        'input_path': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'input', 'comploinc.owl'),
        'code_system_id': 'comp-loinc',
        'native_uri_stems': ['https://loinc.org/'],
    },
    'HPO': {
        'download_url': 'https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/hp-full.owl',
        'code_system_url': 'http://purl.obolibrary.org/obo/hp.owl',
        'input_path': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'input', 'hpo.owl'),
        'code_system_id': 'HPO',
        'native_uri_stems': ['http://purl.obolibrary.org/obo/HP_'],
    },
    'rxnorm': {
        'download_url': 'https://data.bioontology.org/'
                        'ontologies/RXNORM/submissions/23/download?apikey=8b5b7825-538d-40e0-9e9e-5ab9274a9aeb',
        'code_system_url': 'http://purl.bioontology.org/ontology/RXNORM',
        'input_path': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'input', 'RXNORM.ttl'),
        'code_system_id': 'rxnorm',
        'native_uri_stems': ['http://purl.bioontology.org/ontology/RXNORM/'],
    },
    'sequence-ontology': {
        'download_url': 'https://data.bioontology.org/'
                        'ontologies/SO/submissions/304/download?apikey=8b5b7825-538d-40e0-9e9e-5ab9274a9aeb',
        'code_system_url': 'http://purl.bioontology.org/ontology/SO',
        'input_path': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'input', 'so.owl'),
        'code_system_id': 'sequence-ontology',
        'native_uri_stems': ['http://purl.obolibrary.org/obo/SO_'],
    },
})


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


def download(url: str, path: str, download_if_cached=True):
    """Download file at url to local path

    :param download_if_cached: If True and file at `path` already exists, download anyway."""
    _dir = os.path.dirname(path)
    if not os.path.exists(_dir):
        os.makedirs(_dir)
    if download_if_cached or not os.path.exists(path):
        with open(path, 'wb') as f:
            response = requests.get(url, verify=False)
            f.write(response.content)


def owl_to_semsql(inpath: str, use_cache=False) -> str:
    """Converts OWL (or RDF, I think) to a SemanticSQL sqlite DB.
    Docs: https://incatools.github.io/ontology-access-kit/intro/tutorial07.html?highlight=semsql
    - Had to change "--rm -ti"  --> "--rm"
    todo: consider using linkml/semantic-sql image which is more up-to-date instead
      https://github.com/INCATools/semantic-sql
      docker run  -v $PWD:/work -w /work -ti linkml/semantic-sql semsql make foo.db
    todo: RDF also supported? not just OWL? (TTL not supported)
    """
    # Vars
    _dir = os.path.dirname(inpath)
    output_filename = os.path.basename(inpath).replace('.owl', '.db').replace('.rdf', '.db').replace('.ttl', '.db')
    outpath = os.path.join(_dir, output_filename)
    command_str = f'docker run -w /work -v {_dir}:/work --rm obolibrary/odkfull:dev semsql make {output_filename}'

    # Convert
    if use_cache and os.path.exists(outpath):
        return outpath
    try:
        _run_shell_command(command_str, cwd_outdir=_dir)
    except FileExistsError:
        if not use_cache:
            os.remove(outpath)
            _run_shell_command(command_str, cwd_outdir=_dir)
    return outpath


def owl_to_obograph(inpath: str, native_uri_stems: List[str] = None, use_cache=False) -> str:
    """Convert OWL to Obograph
    # todo: TTL and RDF also supported? not just OWL?"""
    # Vars
    outpath = os.path.join(CACHE_DIR, inpath + '.obographs.json')
    outdir = os.path.dirname(outpath)
    command = f'java -jar {ROBOT_PATH}.jar convert -i {inpath} -o {outpath} --format json'

    # Convert
    if not os.path.exists(outdir):
        os.makedirs(outdir)
    if use_cache and os.path.exists(outpath):
        return outpath
    # todo: Switch back to `bioontologies` when complete: https://github.com/bioprag    matics/bioontologies/issues/9
    # from bioontologies import robot
    # parse_results: robot.ParseResults = robot.convert_to_obograph_local(inpath)
    # graph = parse_results.graph_document.graphs[0]
    _run_shell_command(command)

    # Patch missing roots / etc issue (until resolved: https://github.com/ontodev/robot/issues/1082)
    if native_uri_stems:
        with open(outpath, 'r') as f:
            data = json.load(f)
        nodes = data['graphs'][0]['nodes']
        node_ids = set([node['id'] for node in nodes])
        edges = data['graphs'][0]['edges']
        # edges = [x for x in edges if x['pred'] in missing_nodes_from_important_edge_preds]
        edge_subs = set([edge['sub'] for edge in edges])
        edge_objs = set([edge['obj'] for edge in edges])
        edge_ids = edge_subs.union(edge_objs)
        missing = set([x for x in edge_ids if x not in node_ids])  # all missing
        missing = [x for x in missing if any([x.startswith(y) for y in native_uri_stems])]  # filter

        if missing:
            print(f'INFO: The following nodes were found in Obographs edges, but not nodes. Adding missing '
                  f'declarations: {missing}')
            for node_id in missing:
                nodes.append({'id': node_id})
            with open(outpath, 'w') as f:
                json.dump(data, f)

    return outpath


# todo: This doesn't work until following Obographs issues solved. Moved to semsql intermediary for now.
#  - https://github.com/linkml/linkml/issues/1156
#  - https://github.com/ontodev/robot/issues/1079
#  - https://github.com/geneontology/obographs/issues/89
def obograph_to_fhir(
    inpath: str, out_dir: str, out_filename: str = None, code_system_id: str = None, code_system_url: str = None,
    include_all_predicates=False, native_uri_stems: List[str] = None, dev_oak_path: str = None,
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
        gd: GraphDocument = json_loader.load(inpath, target_class=GraphDocument)
        converter.dump(gd, out_path, include_all_predicates=include_all_predicates)
        # todo: update w/ these params when released
        # converter.dump(
        #     gd, out_path, code_system_id='', code_system_url='', include_all_predicates=include_all_predicates,
        #     native_uri_stems=native_uri_stems, use_curies_native_concepts=False, use_curies_foreign_concepts=True)
    return out_path


# todo: add local dev oak params to this and abstract a general 'run oak' func for this and obographs_to_fhir
def semsql_to_fhir(inpath: str, out_dir: str, out_filename: str = None, include_all_predicates=False) -> str:
    """Convert SemanticSQL sqlite DB to FHIR"""
    # todo: any way to do this using Python API?
    # todo: do I need some way of supplying prefix_map? check: are outputs all URIs?
    # converter.curie_converter = curies.Converter.from_prefix_map(get_default_prefix_map())
    out_path = os.path.join(out_dir, out_filename)
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    preds_flag = ' --include-all-predicates' if include_all_predicates else ''
    command_str = f'runoak -i sqlite:{inpath} dump -o {out_path} -O fhirjson{preds_flag}'
    _run_shell_command(command_str)
    return out_path  # todo: When OAK changes to save multiple files, return out_dir


def owl_to_fhir(
    input_path_or_url: str, out_dir: str = OUTDIR, out_filename: str = None, include_all_predicates=False,
    retain_intermediaries=False, intermediary_type=['obographs', 'semsql'][0], use_cached_intermediaries=False,
    intermediary_outdir: str = None, convert_intermediaries_only=False, native_uri_stems: List[str] = None,
    code_system_id: str = None, code_system_url: str = None, dev_oak_path: str = None,
    dev_oak_interpreter_path: str = None
) -> str:
    """Run conversion"""
    # Download if necessary & determine outpaths
    # todo: this section w/ urls, names, and IDs has too many possible branches and is error prone. simplify by
    #  updating CLI params to require url or path separately, and maybe require codesystem id
    intermediary_outdir = intermediary_outdir if intermediary_outdir else out_dir
    input_path = input_path_or_url
    url = None
    maybe_url = urlparse(input_path_or_url)
    if maybe_url.scheme and maybe_url.netloc:
        url = input_path_or_url
    if url:
        input_path = os.path.join(CACHE_DIR, out_filename.replace('.json', '.owl'))
        download(url, input_path)
    if not out_filename:
        if not code_system_id:
            code_system_id = '.'.join(os.path.basename(input_path).split('.')[0:-1])  # removes file extension
        out_filename = f'CodeSystem-{code_system_id}.json'
    if not code_system_id and out_filename and out_filename.startswith('CodeSystem-'):
        code_system_id = out_filename.split('-')[1].split('.')[0]

    # Preprocessing: Special cases
    if 'rxnorm' in input_path.lower() or 'rxnorm' in out_filename.lower():
        input_path = _preprocess_rxnorm(input_path)

    # Convert
    if intermediary_type == 'obographs' or input_path.endswith('.ttl'):  # semsql only supports .owl
        intermediary_path = owl_to_obograph(input_path, native_uri_stems, use_cached_intermediaries)
        obograph_to_fhir(
            inpath=intermediary_path, out_dir=intermediary_outdir, out_filename=out_filename,
            code_system_id=code_system_id, code_system_url=code_system_url, native_uri_stems=native_uri_stems,
            include_all_predicates=include_all_predicates, dev_oak_path=dev_oak_path,
            dev_oak_interpreter_path=dev_oak_interpreter_path)
    else:  # semsql
        intermediary_path = owl_to_semsql(input_path, use_cached_intermediaries)
        semsql_to_fhir(
            inpath=intermediary_path, out_dir=intermediary_outdir, out_filename=out_filename,
            include_all_predicates=include_all_predicates)
    if convert_intermediaries_only:
        return intermediary_path

    # Cleanup
    indir = os.path.dirname(input_path)
    template_db_path = os.path.join(indir, '.template.db')
    if os.path.exists(template_db_path):
        os.remove(template_db_path)
    if not retain_intermediaries:
        # noinspection PyUnboundLocalVariable
        os.remove(intermediary_path)
        if intermediary_type == 'semsql':
            # More semsql intermediaries
            intermediary_filename = os.path.basename(intermediary_path)
            os.remove(os.path.join(indir, intermediary_filename.replace('.db', '-relation-graph.tsv.gz')))
    return os.path.join(out_dir, out_filename)


def _run_favorites(
    use_cached_intermediaries: bool = None, retain_intermediaries: bool = None, include_all_predicates: bool = None,
    intermediary_type: str = None, out_dir: str = None, intermediary_outdir: str = None,
    convert_intermediaries_only: bool = None, dev_oak_path: str = None, dev_oak_interpreter_path: str = None,
    favorites: Dict = FAVORITE_ONTOLOGIES
):
    """Convert favorite ontologies"""
    kwargs = {k: v for k, v in locals().items() if v is not None and not k.startswith('__') and k != 'favorites'}
    fails = []
    successes = []
    n = len(favorites)
    i = 0
    for d in favorites.values():
        i += 1
        print('Converting {} of {}: {}'.format(i, n, d['code_system_id']))
        try:
            owl_to_fhir(
                out_filename=f'CodeSystem-{d["code_system_id"]}.json',
                input_path_or_url=d['input_path'] if d['input_path'] else d['download_url'], **kwargs)
            successes.append(d['id'])
        except Exception as e:
            fails.append(d['code_system_id'])
            print('Failed to convert {}: \n{}'.format(d['code_system_id'], e))
    print('SUMMARY')
    print('Successes: ' + str(successes))
    print('Failures: ' + str(fails))


def cli():
    """Command line interface."""
    package_description = 'Convert OWL to FHIR.'
    parser = ArgumentParser(description=package_description)
    parser.add_argument('-i', '--input-path-or-url', required=False, help='URL or path to OWL file to convert.')
    parser.add_argument(
        '-o', '--out-dir', required=False, default=OUTDIR, help='The directory where results should be saved.')
    parser.add_argument(
        '-n', '--out-filename', required=False, help='Filename for the primary file converted, e.g. CodeSystem.')
    parser.add_argument(
        '-s', '--code-system-id', required=False, default=False,
        help="For `fhirjson` only. The code system ID to use for identification on the server uploaded to. "
             "See: https://hl7.org/fhir/resource-definitions.html#Resource.id",)
    parser.add_argument(
        '-S', '--code-system-url', required=False, default=False,
        help="For `fhirjson` only. Canonical URL for the code system. "
             "See: https://hl7.org/fhir/codesystem-definitions.html#CodeSystem.url",)
    parser.add_argument(
        '-p', '--include-all-predicates', action='store_true', required=False, default=False,
        help='Include all predicates in CodeSystem.property and CodeSystem.concept.property, or just is_a/parent?')
    parser.add_argument(
        '-u', '--native-uri-stems', required=False, nargs='+',
        help='A comma-separated list of URI stems that will be used to determine whether a concept is native to '
             'the CodeSystem. For example, for OMIM, the following URI stems are native: '
             'https://omim.org/entry/,https://omim.org/phenotypicSeries/PS"'
             'As of 2023-01-15, there is still a bug in the Obographs spec and/or `robot` where certain nodes are not'
             ' being converted. This converter adds back the nodes, but to know which ones belong to the CodeSystem '
             'itself and are not foreign concepts, this parameter is necessary. OAK also makes use of this parameter. '
             'See also: https://github.com/geneontology/obographs/issues/90')
    parser.add_argument(
        '-t', '--intermediary-type', choices=INTERMEDIARY_TYPES, default='obographs', required=False,
        help='Which type of intermediary to use? First, we convert OWL to that intermediary format, and then we '
             'convert that to FHIR.')
    parser.add_argument(
        '-c', '--use-cached-intermediaries', action='store_true', required=False, default=False,
        help='Use cached intermediaries if they exist?')
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
    parser.add_argument(
        '-f', '--favorites', action='store_true', default=False, required=False,
        help='If present, will run all favorite ontologies found in `FAVORITE_ONTOLOGIES`. If using this option, the '
             'other CLI flags are not relevant. Instead, edit the following config: `FAVORITE_DEFAULTS`.')

    d: Dict = vars(parser.parse_args())
    if d['favorites']:
        _run_favorites(
            dev_oak_path=d['dev_oak_path'], dev_oak_interpreter_path=d['dev_oak_interpreter_path'],
            **{**FAVORITE_DEFAULTS, **{'favorites': FAVORITE_ONTOLOGIES}})
    del d['favorites']
    owl_to_fhir(**d)


# Execution
if __name__ == '__main__':
    cli()
