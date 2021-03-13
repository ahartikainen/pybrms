# AUTOGENERATED! DO NOT EDIT! File to edit: core.ipynb (unless otherwise specified).

__all__ = ['get_brms_data', 'get_stan_code', 'fit']

# Cell
#hide
import os
import typing
import pandas as pd
import numpy as np
import re

import rpy2.robjects.packages as rpackages
from rpy2.robjects import default_converter, pandas2ri, numpy2ri, ListVector, DataFrame, StrVector
from rpy2.robjects.conversion import localconverter

try:
    brms = rpackages.importr("brms")
except:
    utils = rpackages.importr("utils")
    utils.chooseCRANmirror(ind=1)
    utils.install_packages(StrVector(('brms',)))
    brms = rpackages.importr("brms")

# Cell
def get_brms_data(dataset_name:str):
    "A helper function for importing different datasets included in brms."
    with localconverter(default_converter + pandas2ri.converter + numpy2ri.converter) as cv:
        return pd.DataFrame(rpackages.data(brms).fetch(dataset_name)[dataset_name])

# Cell
def _convert_python_to_R(data: typing.Union[dict, pd.DataFrame]):
    """
    Converts a python object to an R object brms can handle:
    * python dict      ->   R list
    * python dataframe ->   R dataframe
    """
    with localconverter(default_converter + pandas2ri.converter + numpy2ri.converter) as cv:
        if isinstance(data, pd.DataFrame):
            return DataFrame(data)
        elif isinstance(data, dict):
            return ListVector(data)
        else:
            raise ValueError("Data should be either a pandas dataframe or a dictionary")

# Cell
def get_stan_code(
    formula: str,
    data: typing.Union[dict, pd.DataFrame],
    priors: list,
    family: str,
    sample_prior: str="no"
):
    if len(priors)>0:
        return brms.make_stancode(
            formula=formula, data=data, prior=priors, family=family, sample_prior=sample_prior
        )[0]
    else:
        return brms.make_stancode(
            formula=formula, data=data, family=family, sample_prior=sample_prior
        )[0]

# Cell
def _convert_R_to_python(
    formula: str, data: typing.Union[dict, pd.DataFrame], family: str
):
    # calls brms to preprocess the data; returns an R ListVector
    model_data = brms.make_standata(formula, data, family=family)

    # a context manager for conversion between R objects and python/pandas/numpy
    # we're not activating it globally because it conflicts with creation of priors
    with localconverter(default_converter + pandas2ri.converter + numpy2ri.converter) as cv:
        model_data = dict(model_data.items())
    return model_data

# Cell
def _coerce_types(stan_code, stan_data):
    pat_data = re.compile(r'(?<=data {)[^}]*')
    pat_identifiers = re.compile(r'([\w]+)')

    # extract the data block and separate lines
    data_lines = pat_data.findall(stan_code)[0].split('\n')

    # remove commets, <>-style bounds and []-style data size declarations
    data_lines_no_comments = [l.split('//')[0] for l in data_lines]
    data_lines_no_bounds = [re.sub('<[^>]+>', '',l) for l in data_lines_no_comments]
    data_lines_no_sizes = [re.sub('\[[^>]+\]', '',l) for l in data_lines_no_bounds]

    # extract identifiers - first one should be the type, last one should be the name
    identifiers = [pat_identifiers.findall(l) for l in data_lines_no_sizes]
    var_types = [l[0] for l in identifiers if len(l)>0]
    var_names = [l[-1] for l in identifiers if len(l)>0]
    var_dict = dict(zip(var_names, var_types))

    # coerce integers to int and 1-size arrays to scalars
    for k,v in stan_data.items():
        if k in var_names and var_dict[k]=="int":
            stan_data[k] = v.astype(int)
        if v.size==1:
            stan_data[k] = stan_data[k][0]
    return stan_data


# Cell
def fit(
    formula: str,
    data: typing.Union[dict, pd.DataFrame],
    priors: list = [],
    family: str = "gaussian",
    sample_prior: str = "no",
    sample:bool = "yes",
    backend: str= "pystan",
     **pystan_args,
):
    formula = brms.bf(formula)
    data = _convert_python_to_R(data)

    if len(priors)>0:
        brms_prior = brms.prior_string(*priors[0])
        for p in priors[1:]:
            brms_prior = brms_prior + brms.prior_string(*p)
        assert brms.is_brmsprior(brms_prior)
    else:
        brms_prior = []

    model_code = get_stan_code(
        formula=formula,
        data=data,
        family=family,
        priors=brms_prior,
        sample_prior=sample_prior,
    )
    model_data = _convert_R_to_python(formula, data, family)
    model_data = _coerce_types(model_code, model_data)

    if backend == "cmdstanpy":
        from cmdstanpy import CmdStanModel
        import tempfile
        with tempfile.TemporaryDirectory(prefix="pybrms_") as tmp_dir:
            stan_file = os.path.join(tmp_dir, "stan_model.stan")
            with open(stan_file, "w") as fh:
                fh.write(model_code)
            sm = CmdStanModel(stan_file=stan_file)
            if sample==False:
                return sm
            else:
                fit = sm.sample(data=model_data, **pystan_args)
                return fit
    elif backend == "pystan":
        try:
            # pystan 3
            import stan
            sm = stan.build(model_code, data=model_data)
            if sample==False:
                return sm
            else:
                fit = sm.sample(**pystan_args)
                return fit
        except ImportError:
            # pystan 2
            import pystan
            sm = pystan.StanModel(model_code=model_code)
            if sample==False:
                return sm
            else:
                fit = sm.sampling(data=model_data, **pystan_args)
                return fit
    else:
        raise ValueError("Unsupported backend {}. Select from {'cmdstanpy', 'pystan'}".format(backend))