#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Apr 17 23:59:45 2025

@author: rick
"""

import sys
import json
import csv
import yaml

import copy

import pandas as pd
import numpy as np

import matplotlib as mpl

import time
from datetime import datetime
# see https://stackoverflow.com/questions/415511/how-do-i-get-the-current-time-in-python
#   for some basics about datetime

import pprint

# sqlalchemy 2.0 documentation: https://www.sqlalchemy.org/
import psycopg2
from sqlalchemy import create_engine, text as sql_text


# ============================================
#
#  Basic utilities
#
# ============================================

def hello_world():
    return 'hello world'


def time_diff(time1, time2):
    return (time2-time1).total_seconds()

# following https://www.programiz.com/python-programming/datetime/strftime


def format_datetime(dt):
    return dt.strftime("%Y-%m-%d-%H:%M:%S")

# ============================================
#
#  Query building utilities
#
# ============================================

def build_query_listings_join_reviews(date1, date2):
    q = """
SELECT DISTINCT l.id, r.id
FROM listings l, reviews r 
WHERE l.id = r.listing_id
  AND r.date >= '{0}'
  AND r.date <= '{1}'
ORDER BY l.id;"""
    return q.format(date1, date2)

# test:
# print(build_query_listings_join_reviews('2015-01-01', '2015-12-31'))


# ============================================
#
#  Turning list of col-table index pairs into
#     string for use a key in perf_summary.json
#
#  the listing in the key should be ordered
#     according to the listing of all_indexes
#
# ============================================


def build_index_description_key(all_indexes, specs):
    key = '__'
    for index in all_indexes:
        if index in specs:
            key = key + index[0] + '_in_' + index[1] + '__'
    return key

# test
# all_indexes = [['date','reviews'], ['date','calendar'], ['id','listings']]
# spec = [['id','listings'], ['date','reviews']]
# key = build_index_description_key(all_indexes, spec)
# print(str(all_indexes))
# print(key)

# ============================================
#
#  Add/Drop index utility, and print current indexes
#
# ============================================

# this is for single-column indexes;
#    we might play with 2 column indexes,
#    and would need a second function

# the index name is created automatically from
#    index_column and table_name

# i_spec is a 2-element list, e.g., ['date','reviews'] which indicates
#    an index on column 'date' in table 'reviews'.
#    It will be named date_in_reviews
# OR i_spec is a 3-element list, e.g., 
#     << I forget for now, but I think it is related to 
#         text-based indexing ... >>

def add_drop_index(db_eng, add_drop, i_spec):
    # print('\nIn add_drop_index, the value of i_spec is:', str(i_spec))

    # this error checking does NOT check for bad column or relation names
    if len(i_spec) < 2 or len(i_spec) > 3:
        print(
            'ERROR: call to function add_drop_index has invalid i_spec value:', i_spec
            )
        return
    if add_drop not in ['add', 'drop']:
        print(
            'ERROR: call to function add_drop_index has invalid add_drop value:', add_drop
           )

    index_name = i_spec[0] + '_in_' + i_spec[1]
    if add_drop == 'add':
        if len(i_spec) == 2:
            q1 = """
BEGIN TRANSACTION;
CREATE INDEX IF NOT EXISTS {0}
ON {1} ({2});
END TRANSACTION;
"""
            modify_index = q1.format(index_name, i_spec[1], i_spec[0])
            
#             q1 + index_name + q2 + \
#                 i_spec[1] + q3 + i_spec[0] + q4

        elif len(i_spec) == 3:
            q2 = """
            BEGIN TRANSACTION;
CREATE INDEX IF NOT EXISTS {0}
ON {1}
USING {2} ({3});
END TRANSACTION;
"""

            modify_index = q2.format(index_name,
                                     i_spec[1],
                                     i_spec[2],
                                     i_spec[0] )

        else:
            print(
                'ERROR: call to function add_drop_index has invalid i_spec value:', str(i_spec))

    elif add_drop == 'drop':
        q3 = """
BEGIN TRANSACTION;
DROP INDEX IF EXISTS {0};
END TRANSACTION;
"""
        modify_index = q3.format(index_name)
    else:
        print(
            'ERROR: call to function add_drop_index has invalid add_drop value:', add_drop)
        return

    q4 = """SELECT *
FROM pg_indexes
WHERE tablename = '{0}';
"""
    show_indexes = q4.format(i_spec[1])

    # print(show_indexes)
    # print()

    with db_eng.connect() as conn:
        conn.execute(sql_text(modify_index))
        result_indexes = conn.execute(sql_text(show_indexes))

    return result_indexes.fetchall()


# TESTING
# add_test = util.add_drop_index(db_eng, 'add', ['date', 'reviews'])
# print(add_test)

# drop_test = util.add_drop_index(db_eng, 'drop', ['date', 'reviews'])
# print(drop_test)

# bad_test = util.add_drop_index(db_eng, 'add', ['reviews'])
# print(bad_test)



# fetches index info about one table
#   only the indexdef column !
def fetch_index_info(db_eng, table_name):
    q1 = """
SELECT indexdef
FROM pg_indexes
WHERE tablename = '{0}';
"""
    show_indexes = q1.format(table_name)
    with db_eng.connect() as conn:
        result_info = conn.execute(sql_text(show_indexes))

    result_list = result_info.fetchall()

    d = []
    if result_list == []:
        pass
    else:
        for i in range(0, len(result_list)):
            d.append(result_list[i])

    return d

# have not tested this yet in 2025
def fetch_all_index_info(db_eng, index_pair_list):
    dict = {}
    # same tablename may show up in multiple index_pairs,
    #     but dict will have unique table names

    for p in index_pair_list:
        dict[p[1]] = []
    for n in dict:
        temp = []
        temp.append(fetch_index_info(db_eng, n))
        if temp == []:
            dict[n] = []
        else:
            temp1 = []
            for el in temp[0]:
                # the elements from fetch_index... are 1-tuples
                temp1.append(el[0])
            dict[n] = temp1
    return dict
