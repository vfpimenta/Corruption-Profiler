#!/usr/bin/python3

from profiler import Profiler
from optparse import OptionParser
from scipy.stats import spearmanr, pearsonr

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import seaborn as sns

import random
import json
import shutil
import csv
import os

import kde_joyplot
import cluster_eval
import classifier
import util

parser = OptionParser()
parser.add_option('-k', '--k-neighbors', dest='k', type='str',
    help='Number of neighbors for knn', metavar='NUMBER(S)')
parser.add_option('-m', '--method', dest='method', type='str',
    help='Distance method [robust|JS|cosine|all]', metavar='STRING')
parser.add_option('-f', '--function', dest='func', type='str',
    help='Function for evaluation [avg|dist|both]', metavar='STRING')
parser.add_option('-t', '--series-type', dest='series_type', type='str',
    help='Input series [flight|publicity|telecom]', metavar='STRING')
parser.add_option('-s', '--split', dest='split', type='str',
    help='Split type [annually|semiannual|quarterly]', metavar='STRING')
parser.add_option('-p', '--presences', dest='presences', action='store_true',
    help='If presences series should be used')
parser.add_option('-e', '--export', dest='save', action='store_true',
    help='Save results on /img')
parser.add_option('-c', '--compute-silhouette', dest='evaluate_clusters', 
  action='store_true', help='Run silhouette evaluation over clusters')

(options, args) = parser.parse_args()

def get_date_range(legislature, section):
  datelist = pd.date_range(start="2009-04", freq='M', end="2016-09")
  return {
    53: datelist[0:22],
    54: datelist[22:70],
    55: datelist[70:89]
  }[legislature][section[0]:section[1]]

def read_mstknn_dump(legislature, series_type, k, method='JS'):
  with open('../data/{}/dump/{}/k-{}/dump-clusters-{}.json'.format(series_type, method, k, legislature)) as jsonfile:    
    data = json.load(jsonfile)

  return data

def merge_min_clusters(clusters, min_value, legislature):
  merged = list()
  min_cluster = list()
  for cluster in clusters:
    if isinstance(cluster,list):
      if len(cluster) <= min_value:
        min_cluster = min_cluster + cluster
      else:
        merged.append(cluster)
    elif isinstance(cluster, str):
      min_cluster.append(cluster)

  if len(min_cluster) > 0:
    merged.append(min_cluster)

  filepath = '__pycache__/term-{}-cluster-{}.out'.format(legislature,random.randint(10000,99999))
  with open(filepath, 'w') as file:
    file.write(str(merged))

  print('[DEBUG] Merged clusters into min size {}'.format(min_value))
  print('[DEBUG] The final clusters can be fount on {}'.format(filepath))
  return merged

def evaluate_avg(cluster, series, section, presences):
  avgs = list()

  for i in range(section[0], section[1]):
    avg = list()
    for congressman_id in cluster:
      if congressman_id in series.keys():
        try:
          avg.append(series.get(congressman_id)[4][i])
        except Exception as e:
          print(congressman_id)
          print(series.get(congressman_id))
          raise e

    avgs.append(np.average(avg))

  return avgs

def evaluate_dist(cluster, series, section, presences):
  dist = list()

  for congressman_id in cluster:
    if congressman_id in series.keys():
      dist.append(np.average(series.get(congressman_id)[4][section[0]:section[1]]))

  return dist

def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]

def get_sections(legislature, series, split=None):
  expense_length = len(next(iter(series.values()))[4])
  idxs = range(expense_length)

  if legislature == 53 or legislature == 55:
    raise Exception('Not implemented yet!')
  else:
    if split == None:
      return [(0, expense_length)]
    elif split == 'quarterly':
      return [(chunk[0], chunk[-1]) for chunk in chunks(idxs, 3)]
    elif split == 'semiannual':
      return [(chunk[0], chunk[-1]) for chunk in chunks(idxs, 6)]
    elif split == 'annually':
      return [(chunk[0], chunk[-1]) for chunk in chunks(idxs, 12)]

def main(legislatures, k, func, method='JS', series_type='default', split=None, presences=False, evaluate_clusters=False, save=False):

  if series_type == 'default':
    subquota_description = None
  elif series_type == 'flight':
    subquota_description = 'Flight ticket issue'
  elif series_type == 'publicity':
    subquota_description = 'Publicity of parliamentary activity'
  elif series_type == 'telecom':
    subquota_description = 'Telecommunication'
  elif series_type == 'fuels':
    subquota_description = 'Fuels and lubricants'

  profiler = Profiler(light=True)
  for legislature in legislatures:
    series = profiler.read_congressman_json(legislature, subquota_description=subquota_description, presences=presences)
    clusters = merge_min_clusters(read_mstknn_dump(legislature, series_type, k, method), 3, legislature)
    cluster_idx = 0

    # =========================================================================
    # Cluster evaluation module
    if evaluate_clusters:
      file = '../img/{}/silhouette/{}_k{}.png'.format(series_type, method, k)
      if os.path.exists(file):
        os.remove(file)

      cluster_eval._silhouette(clusters, method, k, series_type)
      return
    # =========================================================================

    # =========================================================================
    # Presences correlation module
    if presences:
      expense_series = profiler.read_congressman_json(legislature, subquota_description=subquota_description, presences=False)

      pearson_scores = list()
      spearman_scores = list()
      for congressman_id in series.keys():
        presences_ = series.get(congressman_id)[4]
        expenses_ = expense_series.get(congressman_id)[4]

        pearson_scores.append(pearsonr(presences_, expenses_))
        spearman_scores.append(spearmanr(presences_, expenses_))

      pearson_score = np.mean(pearson_scores)
      spearman_score = np.mean(spearman_scores)

      print("Average pearson score: {}".format(pearson_score))
      print("Average spearman score: {}".format(spearman_score))
    # =========================================================================

    cluster_results = list()
    for cluster in clusters:
      cluster_idx += 1
      section_idx = 0
      results = [list(), list()]
      for section in get_sections(legislature, series, split):
        section_idx += 1
        fig, ax = plt.subplots( nrows=1, ncols=1 )

        if func == 'avg':
          # ===================================================================
          for congressman_id in cluster:
            if congressman_id in series.keys():
              dfs = pd.DataFrame(series.get(congressman_id)[4][section[0]:section[1]], index=get_date_range(legislature, section))
              dfs.plot(ax=ax, legend=False, color="blue", alpha=0.1)
          # ===================================================================

          result = evaluate_avg(cluster, series, section, presences)
          df = pd.DataFrame(result, index=get_date_range(legislature, section))
          df.plot(ax=ax, legend=False, color="black")
          cluster_results.append(result)
        elif func == 'dist':
          result = evaluate_dist(cluster, series, section, presences)
          if np.count_nonzero(result) == 0:
            result = (result + 0.00000001*np.random.randn(len(result))).tolist()
          if len(result) <= 1:
            result = [0.00000001*np.random.rand(), 0.00000001*np.random.rand()]
          sns.distplot(result, norm_hist=True, ax=ax)

        for el in result:
          results[0].append(str(section_idx))
          results[1].append(el)

        if presences:
          series_path = 'presences'
        else:
          series_path = series_type

        if save:
          directory = '../img/{}/graphs/{}/{}/k-{}/term-{}-groups/section-{}'.format(series_path, method, func, k, legislature, section_idx)
          if not os.path.exists(directory):
            os.makedirs(directory)

          fig.savefig('../img/{}/graphs/{}/{}/k-{}/term-{}-groups/section-{}/region-graph-group{}.png'.format(series_path, method, func, k, legislature, section_idx, cluster_idx), bbox_inches='tight')
          plt.close(fig)

      if save and func == 'dist' and split != None:
        df = pd.DataFrame(results)
        df = df.transpose()
        df.columns = ['g', 'x']
        m = df.g.map(ord)

        directory =  '../img/{}/graphs/{}/{}/k-{}/term-{}-groups/kde'.format(series_path, method, func, k, legislature)
        if not os.path.exists(directory):
            os.makedirs(directory)
        kde_joyplot.plot(df, path='../img/{}/graphs/{}/{}/k-{}/term-{}-groups/kde/kde-joyplot-group{}.png'.format(series_path, method, func, k, legislature, cluster_idx))

if __name__ == '__main__':
  series_type = options.series_type
  if not series_type:
    series_type = 'default'

  if options.method == 'all':
    methods = ['robust', 'JS', 'cosine'] 
  else:
    methods = [options.method]

  if options.func == 'both':
    funcs = ['avg', 'dist']
  else:
    funcs = [options.func]

  ks = util.parse_str_list(options.k)

  for itr_method in methods:
    if options.presences:
      path = '../img/{}/graphs/{}'.format('presences', itr_method)
    else:
      path = '../img/{}/graphs/{}'.format(series_type, itr_method)

    if os.path.exists(path) and options.save:
      shutil.rmtree(path)

    for itr_k in ks:
      for itr_func in funcs:
        print('[DEBUG] Running analysis for k={}, method={} and func={}'.format(itr_k, itr_method, itr_func))
        try:
          main([54], itr_k, itr_func, itr_method, series_type=series_type, split=options.split, presences=options.presences, evaluate_clusters=options.evaluate_clusters, save=options.save)
        except Exception as e:
          print(util.bcolors.FAIL+'[ERROR] {}'.format(e)+util.bcolors.ENDC)
          pass