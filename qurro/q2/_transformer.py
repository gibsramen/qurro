#!/usr/bin/env python

import pandas as pd
import qiime2
from qurro.q2._type import QarcoalLogRatiosFormat
from qurro.q2.plugin_setup import plugin

# taken from q2-types/sample_data/_transformer.py
def _read_log_ratios(fh):
    # Using `dtype=object` and `set_index` to avoid type casting/inference
    # of any columns or the index.
    df = pd.read_csv(fh, sep='\t', header=0, dtype=object)
    df.set_index(df.columns[0], drop=True, append=False, inplace=True)
    df.index.name = None
    # casting of columns adapted from SO post:
    # https://stackoverflow.com/a/36814203/3424666
    cols = df.columns
    df[cols] = df[cols].apply(pd.to_numeric, errors='ignore')
    return df

@plugin.register_transformer
def _1(ff: QarcoalLogRatiosFormat) -> qiime2.Metadata:
    return qiime2.Metadata.load(str(ff))

@plugin.register_transformer
def _2(obj: qiime2.Metadata) -> QarcoalLogRatiosFormat:
    ff = QarcoalLogRatiosFormat()
    obj.save(str(ff))
    return ff

@plugin.register_transformer
def _3(data: pd.Series) -> QarcoalLogRatiosFormat:
    ff = QarcoalLogRatiosFormat()
    with ff.open() as fh:
        data.to_csv(fh, sep = '\t', header=True)
    return ff

# taken from q2-types/sample_data/_transformer.py
@plugin.register_transformer
def _4(ff: QarcoalLogRatiosFormat) -> pd.Series:
    with ff.open() as fh:
        df = _read_log_ratios(fh)
        series = df.iloc[:,0]
    return series
