#!/usr/bin/env python3
# ----------------------------------------------------------------------------
# Copyright (c) 2018--, rankratioviz development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE.txt, distributed with this software.
#
# Generates two JSON files: one for a rank plot and one for a sample
# scatterplot of log ratios.
#
# A lot of the code for processing input data in this file was based on code
# by Jamie Morton, some of which is now located in ipynb/Figure3.ipynb in
# https://github.com/knightlab-analyses/reference-frames.
#
# NOTE: For some reason, the sample plot JSON generated here differs somehow
# from the JSON generated by the notebook I was testing this with. Seems to
# just be an ordering issue, but a TODO is to write code that validates that
# that is the case (and it isn't actually messing up any of the data/metadata).
# ----------------------------------------------------------------------------

import json
import sys
import os
import numpy as np
import pandas as pd
from biom import load_table
import altair as alt
from skbio import OrdinationResults
from matplotlib.colors import rgb2hex
from matplotlib import cm

def matchdf(df1,df2):
    idx = set(df1.index) & set(df2.index)
    return df1.loc[idx],df2.loc[idx]

def process_input(ordination_file, biom_table, metadata, taxam=None):
    """Load input files: ordination taxa, BIOM table, metadata."""
    V = ordination_file.features
    U = ordination_file.samples
    table = biom_table.to_dataframe().to_dense().T
    #match 
    table,V = matchdf(table.T,V)
    table,U = matchdf(table.T,U)

    if taxam is not None:
        # match and relabel 
        taxam,V = matchdf(taxam,V)
        if 'Taxon' in taxam.columns \
            and 'Confidence' in taxam.columns:
            #combine and replace
            taxam["Taxon_"] = [(str(x)+'|('+str(y)[:4]+')').replace(' ','')+'|'+str(seq_) 
                               for seq_,x,y in zip(taxam.index,
                                                   taxam.Taxon,
                                                   taxam.Confidence)]
            V.index = taxam["Taxon_"].values
            table.columns = taxam["Taxon_"].values
        elif 'Taxon' in taxam.columns:
            #only taxa
            V.index = taxam["Taxon"].values
            table.columns = taxam["Taxon"].values

    return U, V, table, metadata

def gen_rank_plot(U, V, rank_col):
    """Generates JSON for the rank plot.

    Arguments:

    
    U: sample ranks 
    V: feature ranks 
    rank_col: the column index to use for 
              getting the rank values for each
              taxon.

    Returns:

    altair.Chart object for the rank plot.

    """

    # Get stuff ready for the rank plot

    # coefs is a pandas Series
    coefs = V[rank_col].sort_values()
    # x is a numpy ndarray
    x = np.arange(coefs.shape[0])

    # Set default classification of every taxon to "None"
    # (This value will be updated when a taxon is selected in the rank plot as
    # part of the numerator, denominator, or both parts of the current log
    # ratio.)
    classification = pd.Series(index=coefs.index).fillna("None")
    postFlareRanksData = pd.DataFrame({
        'x': x, 'coefs': coefs, "classification": classification
    })
    # NOTE: The default size value of mark_bar() causes an apparent offset in
    # the interval selection (we're not using that right now, except for the
    # .interactive() thing, though, so I don't think this is currently
    # relevant).
    #
    # Setting size to 1.0 fixes this; using mark_rule() also fixes this,
    # probably because the lines in rule charts are just lines with a width
    # of 1.0.
    postflare_rank_chart = alt.Chart(
            postFlareRanksData.reset_index(),
            title="Ranks"
    ).mark_bar().encode(
        x=alt.X('x', title="Taxa", type="quantitative"),
        y=alt.Y('coefs', title="Ranks", type="quantitative"),
        color=alt.Color("classification",
            scale=alt.Scale(
                domain=["None", "Numerator", "Denominator", "Both"],
                range=["#e0e0e0", "#f00", "#00f", "#949"]
            )
        ),
        size=alt.value(1.0),
        tooltip=["x", "coefs", "classification", "index"]
    ).configure_axis(
        # Done in order to differentiate "None"-classification taxa from grid
        # lines (an imperfect solution to the problem mentioned in the NOTE
        # below)
        gridOpacity=0.35
    ).interactive()
    return postflare_rank_chart

def gen_sample_plot(table, metadata, category,palette='Set1'):
    """Create Altair version of sample scatterplot.

    Arguments:

    table: pandas DataFrame describing taxon abundances for each sample.
    metadata: pandas DataFrame describing metadata for each sample.

    Returns:

    JSON (in the form of a dict) describing the sample plot.
    """

    # Since we don't bother setting a default log ratio, we set the balance for
    # every sample to NaN so that Altair will filter them out (producing an empty
    # scatterplot by default, which makes sense).
    balance = pd.Series(index=table.index).fillna(float('nan'))
    data = pd.DataFrame({'balance': balance}, index=table.index)
    data = pd.merge(data, metadata[[category]], left_index=True, right_index=True)

    # Construct unified DataFrame, combining our "data" DataFrame with the
    # "table" variable (in order to associate each sample with its corresponding
    # abundances)
    sample_metadata_and_abundances = pd.merge(
        data, table, left_index=True, right_index=True
    )

    # "Reset the index" -- make the sample IDs a column (on the leftmost side)
    sample_metadata_and_abundances.reset_index(inplace=True)

    # Make note of the column names in the unified data frame.
    # This constructs a dictionary mapping the column names to their integer
    # indices (just the range of [0, 3084]). Similarly to smaa_i2sid above,
    # we'll preserve this in the JSON.
    smaa_cols = sample_metadata_and_abundances.columns
    smaa_cn2si = {}
    int_smaa_col_names = [str(i) for i in range(len(smaa_cols))]
    for j in int_smaa_col_names:
        # (Altair doesn't seem to like accepting ints as column names, so we
        # mostly use the new column names as strings when we can.)
        smaa_cn2si[smaa_cols[int(j)]] = j

    # Now, we replace column names (which include upwards of 3,000 lineages)
    # with just the integer indices from before.
    #
    # This saves *a lot* of space in the JSON file for the sample plot, since
    # each column name is referenced once for each sample (and
    # 50 samples * (~3000 taxonomy IDs ) * (~50 characters per ID)
    # comes out to 7.5 MB, which is an underestimate).
    sample_metadata_and_abundances.columns = int_smaa_col_names

    #color palette chnage here
    # TODO remove reliance on matplotlib for this and rgb2hex if possible
    set_size = int(len(set(metadata[category])))
    cmap = cm.get_cmap(palette, set_size)

    
    # Create sample plot in Altair.
    sample_logratio_chart = alt.Chart(
        sample_metadata_and_abundances,
        title="Log Ratio of Abundances in Samples"
    ).mark_circle().encode(
        alt.X(smaa_cn2si[category], title=str(category)),
        alt.Y(smaa_cn2si["balance"], title="log(Numerator / Denominator)"),
        color=alt.Color(
            smaa_cn2si[category],
            title=str(category),
            scale=alt.Scale(
                domain=list(set(metadata[category])),
                range=[rgb2hex(cmap(i)) for i in range(set_size)]
            )
        ),
        tooltip=[smaa_cn2si["index"]]
    )#.interactive()

    # Save JSON for sample plot (including the column-identifying dict from
    # earlier).
    sample_logratio_chart_json = sample_logratio_chart.to_dict()
    sample_logratio_chart_json["datasets"]["col_names"] = smaa_cn2si
    return sample_logratio_chart_json
