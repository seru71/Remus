import logging
import re
from collections import OrderedDict

from flask import g

from remus.bio.bed.beds_operations import BedsMutualOperation, BedsFlanker


class BedsProcessor:
    @staticmethod
    def get_genes_beds(genes, genome, *args):
        genome = convert_genome_name(genome, desirable_older_format="hg37")
        genes_beds = [g.genes_registry.get_bed(genome, gene) for gene in genes]
        return [BedsMutualOperation(genes_beds, operation="union").result]

    @staticmethod
    def get_transcription_starting_sites_fantom5_beds(genes, genome, flank_range, upstream, downstream, *args):
        tss_genes = BedsProcessor._get_joined_flanked_genes(genes, genome, upstream, downstream)
        promoters = g.tss_registry.get_bed()
        return [
            BedsMutualOperation([tss_genes, promoters], operation="intersection", **{"wb": True}).result]

    @staticmethod
    def get_enhancers_fantom5_beds(genes, tissues, genome, flank_range, upstream, downstream, *args):
        tss_genes = BedsProcessor._get_joined_flanked_genes(genes, genome,
                                                            int(float(upstream) * 1000),
                                                            int(float(downstream) * 1000))
        bed = BedsProcessor._get_fantom5_enhancers(tissues)
        if bed and tss_genes:
            joined_f5_enh_tissues = BedsProcessor._process_with_overlapping(flank_range, bed).result
            return [
                BedsMutualOperation([tss_genes, joined_f5_enh_tissues], operation="intersection",
                                    **{"wb": True}).result]
        else:
            return []

    @staticmethod
    def get_enhancers_encode_beds(genes, tissues, genome, flank_range, upstream, downstream, *args):
        tss_genes = BedsProcessor._get_joined_flanked_genes(genes, genome,
                                                            int(float(upstream) * 1000),
                                                            int(float(downstream) * 1000))
        bed = BedsProcessor._get_enhancers_encode_beds(tissues)
        if bed and tss_genes:
            joined_f5_enh_tissues = BedsProcessor._process_with_overlapping(flank_range, bed).result
            return [
                BedsMutualOperation([tss_genes, joined_f5_enh_tissues], operation="intersection",
                                    **{"wb": True}).result]
        else:
            return []

    @staticmethod
    def get_accessible_chromatin_beds(genes, tissues, genome, flank_range, upstream, downstream, *args):
        tss_genes = BedsProcessor._get_joined_flanked_genes(genes, genome,
                                                            int(float(upstream) * 1000),
                                                            int(float(downstream) * 1000))
        bed = BedsProcessor._get_accessible_chromatin_encode_beds(tissues)
        if bed and tss_genes:
            joined_f5_enh_tissues = BedsProcessor._process_with_overlapping(flank_range, bed).result
            return [
                BedsMutualOperation([tss_genes, joined_f5_enh_tissues], operation="intersection",
                                    **{"wb": True}).result]
        else:
            return []

    @staticmethod
    def _process_with_overlapping(flank_range, beds):
        if flank_range == "all":
            return BedsMutualOperation(beds, operation="intersection")
        elif flank_range == "any":
            return BedsMutualOperation(beds, operation="union")
        else:
            return []

    @staticmethod
    def _get_joined_flanked_genes(genes, genome, upstream, downstream):
        genome = convert_genome_name(genome, desirable_older_format="hg19")
        genes_beds = BedsProcessor.get_genes_beds(genes, genome)
        flanked_genes_beds = BedsFlanker(genes_beds, downstream, upstream, genome).results
        return BedsMutualOperation(flanked_genes_beds, operation="union").result

    @staticmethod
    def _get_fantom5_enhancers(tissues):
        results = [g.tissues_registry.get_bed(tissue, "ENH_F5") for tissue in tissues]
        return [i for i in results if i]

    @staticmethod
    def _get_enhancers_encode_beds(tissues):
        results = [g.tissues_registry.get_bed(tissue, "ENH_EN") for tissue in tissues]
        return [i for i in results if i]

    @staticmethod
    def _get_accessible_chromatin_encode_beds(tissues):
        results = [g.tissues_registry.get_bed(tissue, "CHRM") for tissue in tissues]
        return [i for i in results if i]


class BedsCollector:
    genes_params = ["genes", "genome"]

    transcription_fantom5_params = [
        "genes", "genome",
        "transcription-fantom5-range",
        "transcription-fantom5-kbs-upstream",
        "transcription-fantom5-kbs-downstream",
        "transcription-fantom5-used"
    ]

    enhancers_fantom5_params = [
        "genes", "tissues", "genome",
        "enhancers-fantom5-range",
        "enhancers-fantom5-kbs-upstream",
        "enhancers-fantom5-kbs-downstream",
        "enhancers-fantom5-used"
    ]

    enhancers_encode_params = [
        "genes", "tissues", "genome",
        "enhancers-encode-range",
        "enhancers-encode-kbs-upstream",
        "enhancers-encode-kbs-downstream",
        "enhancers-encode-used"
    ]

    accessible_chromatin_encode_params = [
        "genes", "tissues", "genome",
        "accessible-chromatin-encode-range",
        "accessible-chromatin-encode-kbs-upstream",
        "accessible-chromatin-encode-kbs-downstream",
        "accessible-chromatin-encode-used"
    ]

    def __init__(self, data):
        self._data = data

    def collect_bed_files(self):
        bed_files = OrderedDict([
            ("genes",
             self._get_bed_files(
                 self.genes_params,
                 BedsProcessor.get_genes_beds)
             ),
            ("transcription-fantom5",
             self._get_bed_files(
                 self.transcription_fantom5_params,
                 BedsProcessor.get_transcription_starting_sites_fantom5_beds)
             ),
            ("enhancers-fantom5",
             self._get_bed_files(
                 self.enhancers_fantom5_params,
                 BedsProcessor.get_enhancers_fantom5_beds)
             ),
            ("enhancers-encode",
             self._get_bed_files(
                 self.enhancers_encode_params,
                 BedsProcessor.get_enhancers_encode_beds)
             ),
            ("accessible-chromatin-fantom5",
             self._get_bed_files(
                 self.accessible_chromatin_encode_params,
                 BedsProcessor.get_accessible_chromatin_beds)
             )
        ])
        return bed_files

    def _get_bed_files(self, params, getter_method):
        params_values = [self._data.get(p) for p in params]
        if all(params_values):
            logging.error("All values provided, running {}".format(getter_method.__name__))
            return getter_method(*params_values)
        else:
            logging.error("NOT all values provided for {} => values:{}".format(getter_method.__name__, params_values))
            return []


def get_matching_genes(pattern, genome_name, limit):
    genome_name = convert_genome_name(genome_name)
    if pattern and genome_name and (genome_name in g.genes_registry.available_genomes):
        return g.genes_registry.get_matching_genes(genome_name, pattern, limit)
    else:
        return []


def get_matching_tissues(pattern, limit):
    return g.tissues_registry.get_matching_tissues(pattern, limit)


def convert_genome_name(genome, desirable_older_format="hg37"):
    if re.match("(hg37|hg19)", genome, re.IGNORECASE):
        return desirable_older_format
    else:
        return genome.lower()

# TODO tu flankujesz promotory, a nam chodzi o znalezienie promotorów w rejonach flankujacych geny,
# TODO trzebaby dodac jeszcze jeden arg dla tej funkcji - genes/transcripts
# TODO tu flankujesz enhancery, a nam chodzi o znalezienie enhancerów w rejonach flankujacych geny,
# TODO wiec trzebaby dodac jeszcze jeden arg dla tej funkcji - genes/transcripts
