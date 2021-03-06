################################################################################
#
# Package   : AlphaPy
# Module    : data
# Created   : July 11, 2013
#
# Copyright 2017 ScottFree Analytics LLC
# Mark Conway & Robert D. Scott II
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
################################################################################


#
# Imports
#

from alphapy.frame import Frame
from alphapy.frame import frame_name
from alphapy.frame import read_frame
from alphapy.globals import ModelType
from alphapy.globals import Partition, datasets
from alphapy.globals import PSEP, SSEP
from alphapy.globals import SamplingMethod
from alphapy.globals import WILDCARD

from datetime import datetime
from datetime import timedelta
from imblearn.combine import SMOTEENN
from imblearn.combine import SMOTETomek
from imblearn.ensemble import BalanceCascade
from imblearn.ensemble import EasyEnsemble
from imblearn.over_sampling import RandomOverSampler
from imblearn.over_sampling import SMOTE
from imblearn.under_sampling import ClusterCentroids
from imblearn.under_sampling import CondensedNearestNeighbour
from imblearn.under_sampling import EditedNearestNeighbours
from imblearn.under_sampling import InstanceHardnessThreshold
from imblearn.under_sampling import NearMiss
from imblearn.under_sampling import NeighbourhoodCleaningRule
from imblearn.under_sampling import OneSidedSelection
from imblearn.under_sampling import RandomUnderSampler
from imblearn.under_sampling import RepeatedEditedNearestNeighbours
from imblearn.under_sampling import TomekLinks
import logging
import numpy as np
import pandas as pd
import pandas_datareader.data as web
import re
import requests
from scipy import sparse
from sklearn.preprocessing import LabelEncoder


#
# Initialize logger
#

logger = logging.getLogger(__name__)


#
# Function get_data
#

def get_data(model, partition):
    r"""Get data for the given partition.

    Parameters
    ----------
    model : alphapy.Model
        The model object describing the data.
    partition : alphapy.Partition
        Reference to the dataset.

    Returns
    -------
    X : pandas.DataFrame
        The feature set.
    y : pandas.Series
        The array of target values, if available.

    """

    logger.info("Loading Data")

    # Extract the model data

    directory = model.specs['directory']
    extension = model.specs['extension']
    features = model.specs['features']
    model_type = model.specs['model_type']
    separator = model.specs['separator']
    target = model.specs['target']
    test_file = model.test_file
    train_file = model.train_file

    # Read in the file

    filename = datasets[partition]
    input_dir = SSEP.join([directory, 'input'])
    df = read_frame(input_dir, filename, extension, separator)

    # Assign target and drop it if necessary

    y = np.empty([0, 0])
    if target in df.columns:
        logger.info("Found target %s in data frame", target)
        # check if target column has NaN values
        nan_count = df[target].isnull().sum()
        if nan_count > 0:
            logger.info("Found %d records with NaN target values", nan_count)
            logger.info("Labels (y) for %s will not be used", partition)
        else:
            # assign the target column to y
            y = df[target]
            # encode label only for classification
            if model_type == ModelType.classification:
                 y = LabelEncoder().fit_transform(y)
            logger.info("Labels (y) found for %s", partition)
        # drop the target from the original frame
        df = df.drop([target], axis=1)
    else:
        logger.info("Target %s not found in %s", target, partition)

    # Extract features

    if features == WILDCARD:
        X = df
    else:
        X = df[features]

    # Labels are returned usually only for training data
    return X, y


#
# Function shuffle_data
#

def shuffle_data(model):
    r"""Randomly shuffle the training data.

    Parameters
    ----------
    model : alphapy.Model
        The model object describing the data.

    Returns
    -------
    model : alphapy.Model
        The model object with the shuffled data.

    """

    # Extract model parameters.

    seed = model.specs['seed']
    shuffle = model.specs['shuffle']

    # Extract model data.

    X_train = model.X_train
    y_train = model.y_train

    # Shuffle data

    if shuffle:
        logger.info("Shuffling Training Data")
        np.random.seed(seed)
        new_indices = np.random.permutation(y_train.size)
        model.X_train = X_train[new_indices]
        model.y_train = y_train[new_indices]
    else:
        logger.info("Skipping Shuffling")

    return model


#
# Function sample_data
#

def sample_data(model):
    r"""Sample the training data.

    Sampling is configured in the ``model.yml`` file (data:sampling:method)
    You can learn more about resampling techniques here [IMB]_.

    Parameters
    ----------
    model : alphapy.Model
        The model object describing the data.

    Returns
    -------
    model : alphapy.Model
        The model object with the sampled data.

    """

    logger.info("Sampling Data")

    # Extract model parameters.

    sampling_method = model.specs['sampling_method']
    sampling_ratio = model.specs['sampling_ratio']
    target = model.specs['target']
    target_value = model.specs['target_value']

    # Extract model data.

    X_train = model.X_train
    y_train = model.y_train

    # Calculate the sampling ratio if one is not provided.

    if sampling_ratio > 0.0:
        ratio = sampling_ratio
    else:
        uv, uc = np.unique(y_train, return_counts=True)
        target_index = np.where(uv == target_value)[0][0]
        nontarget_index = np.where(uv != target_value)[0][0]
        ratio = (uc[nontarget_index] / uc[target_index]) - 1.0
    logger.info("Sampling Ratio for target %s [%r]: %f",
                target, target_value, ratio)

    # Choose the sampling method.

    if sampling_method == SamplingMethod.under_random:
        sampler = RandomUnderSampler()
    elif sampling_method == SamplingMethod.under_tomek:
        sampler = TomekLinks()
    elif sampling_method == SamplingMethod.under_cluster:
        sampler = ClusterCentroids()
    elif sampling_method == SamplingMethod.under_nearmiss:
        sampler = NearMiss(version=1)
    elif sampling_method == SamplingMethod.under_ncr:
        sampler = NeighbourhoodCleaningRule(size_ngh=51)
    elif sampling_method == SamplingMethod.over_random:
        sampler = RandomOverSampler(ratio=ratio)
    elif sampling_method == SamplingMethod.over_smote:
        sampler = SMOTE(ratio=ratio, kind='regular')
    elif sampling_method == SamplingMethod.over_smoteb:
        sampler = SMOTE(ratio=ratio, kind='borderline1')
    elif sampling_method == SamplingMethod.over_smotesv:
        sampler = SMOTE(ratio=ratio, kind='svm')
    elif sampling_method == SamplingMethod.overunder_smote_tomek:
        sampler = SMOTETomek(ratio=ratio)
    elif sampling_method == SamplingMethod.overunder_smote_enn:
        sampler = SMOTEENN(ratio=ratio)
    elif sampling_method == SamplingMethod.ensemble_easy:
        sampler = EasyEnsemble()
    elif sampling_method == SamplingMethod.ensemble_bc:
        sampler = BalanceCascade()
    else:
        raise ValueError("Unknown Sampling Method %s" % sampling_method)

    # Get the newly sampled features.

    X, y = sampler.fit_sample(X_train, y_train)

    logger.info("Original Samples : %d", X_train.shape[0])
    logger.info("New Samples      : %d", X.shape[0])

    # Store the new features in the model.

    model.X_train = X
    model.y_train = y

    return model


#
# Function get_google_data
#

def get_google_data(symbol, lookback_period, fractal):
    r"""Get Google Finance intraday data.

    We get intraday data from the Google Finance API, even though
    it is not officially supported. You can retrieve a maximum of
    50 days of history, so you may want to build your own database
    for more extensive backtesting.

    Parameters
    ----------
    symbol : str
        A valid stock symbol.
    lookback_period : int
        The number of days of intraday data to retrieve, capped at 50.
    fractal : str
        The intraday frequency, e.g., "5m" for 5-minute data.

    Returns
    -------
    df : pandas.DataFrame
        The dataframe containing the intraday data.

    """

    # Google requires upper-case symbol, otherwise not found
    symbol = symbol.upper()
    # convert fractal to interval
    interval = 60 * int(re.findall('\d+', fractal)[0])
    # Google has a 50-day limit
    max_days = 50
    if lookback_period > max_days:
        lookback_period = max_days
    # set Google data constants
    toffset = 7
    line_length = 6
    # make the request to Google
    base_url = 'https://www.google.com/finance/getprices?q={}&i={}&p={}d&f=d,o,h,l,c,v'
    url = base_url.format(symbol, interval, lookback_period)
    response = requests.get(url)
    # process the response
    text = response.text.split('\n')
    records = []
    for line in text[toffset:]:
        items = line.split(',')
        if len(items) == line_length:
            dt_item = items[0]
            close_item = items[1]
            high_item = items[2]
            low_item = items[3]
            open_item = items[4]
            volume_item = items[5]
            if dt_item[0] == 'a':
                day_item = float(dt_item[1:])
                offset = 0
            else:
                offset = float(dt_item)
            dt = datetime.fromtimestamp(day_item + (interval * offset))
            dt = pd.to_datetime(dt)
            dt_date = dt.strftime('%Y-%m-%d')
            record = (dt, dt_date, open_item, high_item, low_item, close_item, volume_item)
            records.append(record)
    # create data frame
    cols = ['datetime', 'date', 'open', 'high', 'low', 'close', 'volume']
    df = pd.DataFrame.from_records(records, columns=cols)
    # convert to proper data types
    cols_float = ['open', 'high', 'low', 'close']
    df[cols_float] = df[cols_float].astype(float)
    df['volume'] = df['volume'].astype(int)
    # number the intraday bars
    date_group = df.groupby('date')
    df['bar_number'] = date_group.cumcount()
    # mark the end of the trading day
    df['end_of_day'] = False
    del df['date']
    df.loc[date_group.tail(1).index, 'end_of_day'] = True
    # set the index to datetime
    df.index = df['datetime']
    del df['datetime']
    # return the dataframe
    return df


#
# Function get_yahoo_data
#

def get_yahoo_data(symbol, lookback_period):
    r"""Get Yahoo Finance daily data.

    Parameters
    ----------
    symbol : str
        A valid stock symbol.
    lookback_period : int
        The number of days of daily data to retrieve.

    Returns
    -------
    df : pandas.DataFrame
        The dataframe containing the intraday data.

    """

    # Calculate the start and end date for Yahoo.

    start = datetime.now() - timedelta(lookback_period)
    end = datetime.now()

    # Call the Pandas Web data reader.

    df = web.DataReader(symbol, 'yahoo', start, end)

    # Set time series as index

    if len(df) > 0:
        df.reset_index(level=0, inplace=True)
        df = df.rename(columns = lambda x: x.lower().replace(' ',''))
        df['datetime'] = pd.to_datetime(df['date'])
        del df['date']
        df.index = df['datetime']
        del df['datetime']

    return df


#
# Function get_feed_data
#

def get_feed_data(group, lookback_period):
    r"""Get data from an external feed.

    Parameters
    ----------
    group : alphapy.Group
        The group of symbols.
    lookback_period : int
        The number of days of data to retrieve.

    Returns
    -------
    daily_data : bool
        ``True`` if daily data

    """

    gspace = group.space
    fractal = gspace.fractal
    # Determine the feed source
    if 'd' in fractal:
        # daily data (date only)
        logger.info("Getting Daily Data")
        daily_data = True
    else:
        # intraday data (date and time)
        logger.info("Getting Intraday Data (Google 50-day limit)")
        daily_data = False
    # Get the data from the relevant feed
    for item in group.members:
        logger.info("Getting %s data for last %d days", item, lookback_period)
        if daily_data:
            df = get_yahoo_data(item, lookback_period)
        else:
            df = get_google_data(item, lookback_period, fractal)
        if len(df) > 0:
            # allocate global Frame
            newf = Frame(item.lower(), gspace, df)
            if newf is None:
                logger.error("Could not allocate Frame for: %s", item)
        else:
            logger.info("Could not get data for: %s", item)
    # Indicate whether or not data is daily
    return daily_data
