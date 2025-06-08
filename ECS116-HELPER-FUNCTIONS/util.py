
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
#  dictionary manipulation utilities
#
# ============================================

def drop_prefixes_in_keys(dict):
    dict1 = {}
    for key in dict:
        parts = key.split('_')
        new_key = parts[-1]
        dict1[new_key] = dict[key]

    return dict1
    


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


# ============================================
#
#  Queries for loading mongodb with Listings join reviews data
#
# ============================================

def build_query_full_join_listings_reviewsm_100():
    q = """select *
from listings l, reviewsm r
where l.id = r.listing_id
  and left(l.id,3) = '100'
-- this query fetches 406 listings, useful for testing"""
    return q

def build_query_full_join_listings_reviewsm_10():
    q = """select *
from listings l, reviewsm r
where l.id = r.listing_id
  and left(l.id,2) = '10'
-- this query fetches data for 3313 listings, useful for testing"""
    return q

def build_query_full_join_listings_reviewsm():
    q = """select *
from listings l, reviewsm r
where l.id = r.listing_id"""
    return q

def build_query_left_join_listings_reviewsm():
    q = """select *
from listings l left join reviewsm r 
        on l.id = r.listing_id"""
    return q

def build_query_left_join_listings_reviewsm_10():
    q = """select *
from listings l left join reviewsm r 
        on l.id = r.listing_id
  where left(l.id,2) = '10'
-- this query fetches data for 3313 listings, useful for testing""" 
    return q

def build_query_left_join_listings_reviewsm_100():
    q = """select *
from listings l left join reviewsm r 
        on l.id = r.listing_id  
  where left(l.id,3) = '100'
-- this query fetches data for 406 listings, useful for testing"""
    return q



# this seems to be poorly named
def build_query_left_join_listings_reviewsm_null_right():
    q = """select *
from listings l left join reviewsm r 
        on l.id = r.listing_id
where     l.id = '47305871'"""
    return q

def build_query_get_all_listing_ids():
    q = """select distinct id as listing_id
from listings
order by id"""
    return q

def build_query_calendar_for_listing(listing_id):
    q = """select date, available, price,
       adjusted_price, minimum_nights, maximum_nights
from calendar
where listing_id = '{}'""".format(listing_id)
    return q




#==================================

#==================================
#==================================

# stuff from 2024 related to PA2

#==================================


def build_query_listings_join_reviews(date1, date2):
    query = """SELECT DISTINCT l.id, l.name
FROM listings l, reviews r 
WHERE l.id = r.listing_id
  AND r.datetime >= '"""
    q32 = """'
  AND r.datetime <= '"""
    q33 = """'
ORDER BY l.id;"""
    return q31 + date1 + q32 + date2 + q33



# left(to_char(date, 'YYYY-MM-DD'),4) as year, count(*)


# ============================================
#
#  Utility to pull the performance info file from perf_data folder,
#     or create the file if it doesn't exist
#
# ============================================

# the key for each entry of perf_dict will be the name of a query or update
# the value for each entry of perf_dict will be a "perf_dict" with keys that
#     list all indexes that were in force at the time of the test run.  E.g.:
#
#        { '__' : ...,                                     -- i.e., no indexes in force
#          '__id_in_listings__' : ...,                     -- indexes in force: { id_in_listings }
#          '__date_in_reviews__' : ...,                    -- indexes in force: { date_in_reviews }
#          '__date_in_reviews__id_in_listings__' : ... }   -- indexes in force: { date_in_reviews, id_in_listings }

# the value for each entry of the inner dict will have be a "performance profile" (perf_prof):
#       having shape {avg: ..., min: ..., max: ..., std: ...}
# (please see below for an example)


# fetches filename (which should be a json file) and returns a
#       dict corresponding to the contents of filename
def fetch_perf_data(filename):
    f = open('perf_data/' + filename)
    return json.load(f)

# writes the dictionary in dict as a json file into filename


def write_perf_data(dict1, filename):
    # for some reason pprint is not sorting by key, so doing it before writing to disk
    dict2 = dict(sorted(dict1.items()))
    with open('perf_data/' + filename, 'w') as fp:
        json.dump(dict2, fp)

# testing:
# test = { 'foo': 'goo', 'foo1' : {'hoo': 'boo', 'zoo': 'loo'}}
# write_perf_data(test, 'test.json')
# dict = fetch_perf_data('test.json')
# pprint.pp(dict, indent=4)

# ============================================
#
#  From Aunsch file "aunsh_util_main.py"
#
# ============================================




def calc_time_diff_per_year(db_eng, count, q_dict):
    perf_details = {}

    # Iterate through all the queries in q_dict
    for year, sql_query in q_dict.items():
        time_list = []        
        for i in range(count): 
            time_start = datetime.now()

            with db_eng.connect() as conn:
                df = pd.read_sql(sql_query, con=conn)

            time_end = datetime.now()
            # Calulate the time difference
            diff = time_diff(time_start, time_end)
            time_list.append(diff)
            
        # Splitting the string to get the year
        parts = year.split('_')
        curr_year = parts[-1]

        # Calulcate the metrics
        perf_profile = {
            'avg': round(sum(time_list) / len(time_list), 4),
            'min': round(min(time_list), 4),
            'max': round(max(time_list), 4),
            'std': round(np.std(time_list), 4)
        }
        # Add metrics according to the year
        perf_details[curr_year] = perf_profile
    return perf_details


# ============================================
#
#  Query building utilities
#
# ============================================



def build_query_listings_join_reviews(date1, date2):
    q31 = """SELECT DISTINCT l.id, l.name
FROM listings l, reviews r 
WHERE l.id = r.listing_id
  AND r.datetime >= '"""
    q32 = """'
  AND r.datetime <= '"""
    q33 = """'
ORDER BY l.id;"""
    return q31 + date1 + q32 + date2 + q33

# test:
# print(build_query_listings_join_reviews('2015-01-01', '2015-12-31'))


# I am loading the query results into a dataframe to make sure that the full
#    value of the query is retrieved by PostgreSQL.  If I retrieve into a
#    cursor, then the system may use "lazy" evaluation and not actually retrieve
#    all the records until I access them later with fetchone() or fetchmany()

# NOTE: you have to "double up" the "%" signs for sqlalchemy to work
#  following https://docs.sqlalchemy.org/en/20/faq/sqlexpressions.html#why-are-percent-signs-being-doubled-up-when-stringifying-sql-statements

def build_query_listings_join_reviews_with_date_not_datetime(date1, date2):
    q31 = """SELECT DISTINCT l.id, l.name
FROM listings l, reviews r 
WHERE l.id = r.listing_id
  AND r.date >= '"""
    q32 = """'
  AND r.date <= '"""
    q33 = """'
ORDER BY l.id;"""
    return q31 + date1 + q32 + date2 + q33


def build_query_word_year_no_ts_index(word, date1, date2):
    q41 = """SELECT *
FROM reviews r 
WHERE comments ILIKE '%%"""
    q42 = """%%' 
  AND date >= '"""
    q43 = """'
  AND date <= '"""
    q44 = """';"""

    return q41 + word + q42 + date1 + q43 + date2 + q44


def build_query_word_year_ts_index(word, date1, date2):
    q51 = """SELECT *
FROM reviews r 
WHERE comments_tsv @@ to_tsquery('"""
    q52 = """')
  AND date >= '"""
    q53 = """'
  AND date <= '"""
    q54 = """';"""

    return q51 + word + q52 + date1 + q53 + date2 + q54

# vec has shape [prange, year, sword]
#    prange has values '0000s', 0100s', ... , '0900s', '1000_and_above'
#    year is an integer
#    sword will generally be one of 'horrible', 'awesome', or 'apartment'
# ts_index is either True or False
# the queries to be built look like:
"""
SELECT *
FROM listings l, reviews r
WHERE l.id = r.listing_id
  AND l.price >= 1000
  AND r.date >= '2023-01-01' and r.date <= '2023-12-31'
  AND comments ilike '%%apartment%%';

SELECT *
FROM listings l, reviews r
WHERE l.id = r.listing_id
  AND l.price >= 800 and l.price < 900
  AND r.date >= '2023-01-01' and r.date <= '2023-12-31'
  AND comments_tsv @@ to_tsquery('awesome');
"""

def build_price_range_year_word(vec, ts_index):
    prange = vec[0]
    year = vec[1]
    sword = vec[2]
    
    q1 = """SELECT *
FROM listings l, reviews r
WHERE l.id = r.listing_id
  AND l.price >= """
    q2 = """ AND l.price < """
    q3 = """
  AND r.datetime >= '"""
    q4 = """-01-01' AND r.datetime <= '"""
    q5nots = """-12-31'
  AND comments ILIKE '%%"""
    q6nots = """%%';"""
    
    q5ts = """-12-31'
  AND comments_tsv @@ to_tsquery('"""
    q6ts = """');"""
    
    if prange != '1000_and_above':
        min = int(prange[0:3])
        max = min + 100  
        prefix = q1 + str(min) + q2 + str(max) + \
                 q3 + str(year) + q4 + str(year) 
    else:
        prefix = q1 + str('1000') + \
                 q3 + str(year) + q4 + str(year) 
                 
    if ts_index:
        q = prefix + q5ts + sword + q6ts
    else:
        q = prefix + q5nots + sword + q6nots
        
    return q
           

"""
select count(*)
from listings l, reviews r
where l.id = r.listing_id
  and r.date >= '2023-01-01' and r.date <= '2023-12-31'
  and comments_tsv @@ to_tsquery('apartment')
  and l.neighbourhood_group = 'Brooklyn'
"""
def build_ngroup_year_sword(vec, ts_index):
    ngroup = vec[0]
    year = vec[1]
    sword = vec[2]
    
    q1 = """SELECT *
FROM listings l, reviews r
WHERE l.id = r.listing_id
  AND l.neighbourhood_group = '"""
    q3 = """'
  AND r.date >= '"""
    q4 = """-01-01' AND r.date <= '"""
    q5nots = """-12-31'
  AND comments ILIKE '%%"""
    q6nots = """%%';"""
    
    q5ts = """-12-31'
  AND comments_tsv @@ to_tsquery('"""
    q6ts = """');"""
    
    prefix = q1 + ngroup +  \
             q3 + str(year) + q4 + str(year) 
                 
    if ts_index:
        q = prefix + q5ts + sword + q6ts
    else:
        q = prefix + q5nots + sword + q6nots
        
    return q
           
def build_ngroup_year_datetime_sword(vec, ts_index):
    ngroup = vec[0]
    year = vec[1]
    sword = vec[2]
    
    q1 = """SELECT count(*)
FROM listings l, reviews r
WHERE l.id = r.listing_id
  AND l.neighbourhood_group = '"""
    q3 = """'
  AND r.datetime >= '"""
    q4 = """-01-01' AND r.datetime <= '"""
    q5nots = """-12-31'
  AND comments ILIKE '%%"""
    q6nots = """%%';"""
    
    q5ts = """-12-31'
  AND comments_tsv @@ to_tsquery('"""
    q6ts = """');"""
    
    prefix = q1 + ngroup +  \
             q3 + str(year) + q4 + str(year) 
                 
    if ts_index:
        q = prefix + q5ts + sword + q6ts
    else:
        q = prefix + q5nots + sword + q6nots
        
    return q






def query_reviews_by_year_counts():
    q = """select left(to_char(date, 'YYYY-MM-DD'),4) as year, count(*)
from reviews
group by year
order by year"""

    return q


def query_listings_price_ranges_counts():
    q = """select 
    case 
	    when price < 100 then '000s'
	    when 100 <= price and price < 200 then '100s'   	
	    when 200 <= price and price < 300 then '200s'   	
	    when 300 <= price and price < 400 then '300s'   	
	    when 400 <= price and price < 500 then '400s'   	
	    when 500 <= price and price < 600 then '500s'   	
	    when 600 <= price and price < 700 then '600s'   	
	    when 700 <= price and price < 800 then '700s'   	
	    when 800 <= price and price < 900 then '800s'   	
	    when 900 <= price and price < 1000 then '900s'   	
	    when 1000 <= price  then '1000_and_above'
	    -- when 2000 <= price and price < 3000 then '2000s'
	    -- when 3000 <= price and price < 4000 then '3000s'
	    -- when 4000 <= price and price < 5000 then '4000s'
	    -- when 5000 <= price then '5000_and_above'
	    when price is null then 'NULL'
	else
	   'mystery'
    end as price_interval,
    count(*)
from listings l 
where room_type = 'Entire home/apt'
group by price_interval
order by price_interval"""

    return q


def query_reviews_words_counts():
    q = """select 
    case 
    	when comments_tsv @@ to_tsquery('horrible') then 'horrible'
    	when comments_tsv @@ to_tsquery('awesome') then 'awesome'
    	when comments_tsv @@ to_tsquery('apartment') then 'apartment'
    end as word,
    count(*)
from reviews r 
group by word
order by word"""

    return q

def query_neighbourhood_groups_listings_counts():
    q = """select count(*), neighbourhood_group
from listings l, reviews r 
where l.id = r.listing_id 
group by neighbourhood_group
order by count desc"""

    return q

def query_neighbourhoods_listings_counts():
    q = """select count(*), neighbourhood, neighbourhood_group
from listings l, reviews r 
where l.id = r.listing_id 
group by neighbourhood, neighbourhood_group
order by count desc"""

    return q

# this builds the following kind of query
"""
update reviews r
set datetime = datetime + interval '5 days'
from listings l
where l.id = r.listing_id
  and l.neighbourhood_group = 'Queens'
RETURNING 'done'
"""

def build_update_ngroup_datetime_in_reviews(db_eng, ngroup, days):
    q1 = """UPDATE reviews r
SET datetime = datetime """
    q2 = """ interval '"""
    q3 = """ days'
FROM listings l
WHERE l.id = r.listing_id
  AND l.neighbourhood_group = '"""
    q4 = """'
RETURNING 'done';"""
    
    if days > 0:
        sign = '+'
    elif days < 0:
        sign = '-'
    else:
        print('ERROR: days value in build_update_ngroup_datetime_in_reviews is zero; it must be postive or negative')
    
    q = q1 + sign + q2 + str(abs(days)) + \
           q3 + ngroup + q4

    return q
    
def build_update_neigh_datetime_in_reviews(db_eng, ngroup, days):
    q1 = """UPDATE reviews r
SET datetime = datetime """
    q2 = """ interval '"""
    q3 = """ days'
FROM listings l
WHERE l.id = r.listing_id
  AND l.neighbourhood = '"""
    q4 = """'
RETURNING 'done';"""
    
    if days > 0:
        sign = '+'
    elif days < 0:
        sign = '-'
    else:
        print('ERROR: days value in build_update_neigh_datetime_in_reviews is zero; it must be postive or negative')
    
    q = q1 + sign + q2 + str(abs(days)) + \
           q3 + ngroup + q4

    return q
       



# ============================================
#
#  Turning list of col-table index pairs into
#     string for use a key in perf_summary.json
#
# ============================================


def build_index_description_key(specs):
    key = '__'
    for index in specs:
        key = key + index[0] + '_in_' + index[1] + '__'
    return key

# test
# all_indexes = [['date','reviews'], ['date','calendar'], ['id','listings']]
# spec = [['id','listings'], ['date','reviews']]
# key = build_index_description_key(all_indexes, spec)
# print(str(all_indexes))
# print(key)

def build_index_description_key_with_ts_index(specs):
    return build_index_description_key(specs) + 'comments_tsv_in_reviews' + '__'
    
def build_index_description_key_no_ts_index(specs):
    return build_index_description_key(specs) 


# ============================================
#
#  Add/Drop index utility, and print current indexes
#
# ============================================

# this is for single-column indexes;
#    we might play with 2 column indexes,
#    and would need a second function

# the index name is created automatically fom
#    index_column and table_name

# i_spec is a 2-element list, e.g., ['date','reviews'] which indicates
#    an index on column 'date' in table 'reviews'.
#    It will be named date_in_reviews

def add_drop_index(db_eng, add_drop, i_spec):
    # print('\nIn add_drop_index, the value of i_spec is:', str(i_spec))
    index_name = i_spec[0] + '_in_' + i_spec[1]
    if add_drop == 'add':
        if len(i_spec) == 2:
            q1 = """BEGIN TRANSACTION;
CREATE INDEX IF NOT EXISTS """
            q2 = """
ON """
            q3 = """("""
            q4 = """);
END TRANSACTION;
"""
            modify_index = q1 + index_name + q2 + \
                i_spec[1] + q3 + i_spec[0] + q4

        elif len(i_spec) == 3:
            q1 = """BEGIN TRANSACTION;
CREATE INDEX IF NOT EXISTS """
            q2 = """
ON """
            q2a = """ USING """
            q3 = """ ("""
            q4 = """);
END TRANSACTION;
    """

            modify_index = q1 + index_name + q2 + i_spec[1] \
                              + q2a + i_spec[2] + q3 + i_spec[0] + q4

        else:
            print(
                'ERROR: call to function add_drop_index has invalid i_spec value:', str(i_spec))

    elif add_drop == 'drop':
        q6 = """BEGIN TRANSACTION;
DROP INDEX IF EXISTS """
        q7 = """;
END TRANSACTION;
"""
        modify_index = q6 + index_name + q7
    else:
        print(
            'ERROR: call to function add_drop_index has invalid add_drop value:', add_drop)
        return

    q8 = """SELECT *
FROM pg_indexes
WHERE tablename = '"""
    q9 = """';
"""
    show_indexes = q8 + i_spec[1] + q9

    # print(show_indexes)
    # print()

    with db_eng.connect() as conn:
        conn.execute(sql_text(modify_index))
        result_indexes = conn.execute(sql_text(show_indexes))

    return result_indexes.fetchall()


# TESTING

# add_test = add_drop_index(db_eng, 'reviews', 'add', 'date_in_reviews', 'date')
# print(add_test)

# drop_test = add_drop_index(db_eng, 'reviews', 'drop', 'date_in_reviews', '')
# print(drop_test)

# bad_test = add_drop_index(db_eng, 'reviews', 'foo', 'date_in_reviews', '')
# print(bad_test)

# fetches index info about one table
#   only the indexdef column !
def fetch_index_info(db_eng, table_name):
    q8 = """SELECT indexdef
FROM pg_indexes
WHERE tablename = '"""
    q9 = """';
"""
    show_indexes = q8 + table_name + q9
    with db_eng.connect() as conn:
        # conn.execute(sql_text(modify_index))
        result_info = conn.execute(sql_text(show_indexes))

    result_list = result_info.fetchall()

    d = []
    if result_list == []:
        pass
    else:
        for i in range(0, len(result_list)):
            d.append(result_list[i])

    return d


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
                # the elements from fetc_index... are 1-tuples
                temp1.append(el[0])
            dict[n] = temp1
    return dict

# ============================================
#
#  Utility to run one test on one query
#    (Assumes that indexes were set up in a
#     preceding step)
#
# ============================================


def run_one_query(db_eng, q, count):
    time_list = []
    for i in range(0, count):
        time_start = datetime.now()
        # Open new db connection for each execution of the query to avoid multithreading
        with db_eng.connect() as conn:
            # conn.execute(sql_text(q3))
            df = pd.read_sql(q, con=conn)
        time_end = datetime.now()
        diff = time_diff(time_start, time_end)
        time_list.append(diff)

    perf_profile = {'avg': round(sum(time_list)/len(time_list), 4),
                    'min': round(min(time_list), 4),
                    'max': round(max(time_list), 4),
                    'std': round(np.std(time_list), 4),
                    'exec_count': count,
                    'timestamp': format_datetime(time_end)
                    }

    return perf_profile, time_list


# ============================================
#
#  Utility to run multiple tests
#  -- all_indexes is the list of all indexes in play (might need to drop some of them)
#  -- q_name is the name of the query to test on
#  -- q is the query to run the tests on
#  -- i_spec is list of index specification pairs () - to be used for the test run
#
# ============================================

# First, a utility

def set_up_indexes(db_eng, all_indexes, i_specs):
    # print('\n\nEntered set_up_indexes for i_spec:', i_spec)
    # first, drop all indexes not in i_specs
    for index in all_indexes:
        if index not in i_specs:
            # print('\nDropping index ', str(index), '; this is in all_indexes but not i_spec')
            mod_index = add_drop_index(db_eng, 'drop', index)
            # print('After doing the drop for', str(index), 'the indexes on table "' + index[1] + '" are: ')
            # print(mod_index)

    # adding all indexes in i_spec
    for index in i_specs:
        # print('\nAdding index ', str(index), '; this was in i_spec')
        mod_index = add_drop_index(db_eng, 'add', index)
        # print('After doing the add for', str(index), 'the indexes on table "' + index[1] + '" are: ')
        # print(mod_index)

    return mod_index


'''
def run_one_query_on_one_index_spec(db_eng, all_indexes, q_name, q, i_spec, count):
    # first, set up the indexes according to i_specs
    set_up_indexes(db_eng, all_indexes, i_spec)

    # will not use the time_list when we run these queries
    perf_profile, time_list = run_one_query(db_eng, q, count)
    
    """
    spec_descrip = build_index_description_key(i_spec)
        
    perf_summary = {}
    perf_summary[q_name] = {}
    perf_summary[q_name][spec_descrip] = perf_profile
    """
    
    return perf_profile
'''


# ============================================
#
#  Utility to run multiple tests
#  -- all_indexes is the list of all indexes in play (might need to drop some of them)
#  -- q_name is the name of the query to test on
#  -- q is the query to run the tests on
#  -- i_spec_list is list of index specification pairs () - to be used for the test run
#  -- perf_file is name of file in perf_data/ to hold outputs, e.g., 'perf_summary.json'
#
# ============================================

# first, a function to build all subsets of [0..count-1]:
def build_all_subsets(count):
    subsets = [[]]
    for i in range(0, count):
        old = copy.deepcopy(subsets)
        for l in subsets:
            l.append(i)
        subsets = copy.deepcopy(old + subsets)
    return subsets
# e.g., on 3 this returns
#    [[], [0], [1], [0, 1], [2], [0, 2], [1, 2], [0, 1, 2]]


def run_one_query_and_multi_index_specs(db_eng, all_indexes, q_name, q, i_spec_list, count):
    # Build set of i_specs that will be used for a series of tests
    # first, build a list of all subsets of numbers in [0..len(i_spec_list)-1]
    subsets = build_all_subsets(len(i_spec_list))

    perf_dict = {}

    # for each set in subsets we do a run for exactly the i_specs whose counter is in the set
    for set in subsets:
        i_spec = []
        for n in set:
            i_spec.append(i_spec_list[n])
        print('\nNow working on the i_spec:', i_spec)

        # set up indexes according to i_spec
        set_up_indexes(db_eng, all_indexes, i_spec)
        print('Current set of indexes in effect is:')
        indexes_in_effect = fetch_all_index_info(db_eng, all_indexes)
        pprint.pp(indexes_in_effect, width=150)

        # run tests on query q_name, q for this index set up
        print('\nNow invoking run_one_query')
        perf_profile, time_listing = run_one_query(db_eng, q, count)

        i_spec_key = build_index_description_key(i_spec)

        perf_dict[i_spec_key] = perf_profile

    return {q_name: perf_dict}


# ============================================
#
#  Utility to fold new performance results into json file of existing results
#  -- perf_file is the file to be added to
#  -- perf_summary is the new performance data to be foled into perf_file
#
# ============================================


# this one does a kind of "deep" merge of the new perf_profile with the existing
#    perf_file.  Another fetch_and_update defined below does a moe "shallow" 
#    merge.  

def fetch_and_update_perf_data_deeper_merge(perf_file, new_perf_summary):
    # fetch or create file perf_data/perf_file
    # print('\nEntering fetch_and_update_perf_data')
    try:
        old_perf_summary = fetch_perf_data(perf_file)
        # print('Successfully read file perf_data/' + perf_file)
        # print('\nValue of old_perf_summary is:')
        # pprint.pp(old_perf_summary)
    except:
        print('Not successful in finding file perf_data/' +
              perf_file + '; so creating it')
        old_perf_summary = {}
        write_perf_data(old_perf_summary, perf_file)

    # structure of perf_summary
    #    query_name : index_descrip : perf_profile

    # print('\nValue of new_perf_summary is:')
    # pprint.pp(new_perf_summary)

    for q_name in new_perf_summary:
        if q_name in old_perf_summary:
            for i_key in new_perf_summary[q_name]:
                # in this case, clobber old value for i_key with new value for i_key
                old_perf_summary[q_name][i_key] = new_perf_summary[q_name][i_key]
        else:
            old_perf_summary[q_name] = new_perf_summary[q_name]

    write_perf_data(old_perf_summary, perf_file)
    return old_perf_summary

def fetch_and_update_perf_data_deeper_merge_ts(perf_file, new_perf_summary):
    # fetch or create file perf_data/perf_file
    # print('\nEntering fetch_and_update_perf_data')
    try:
        old_perf_summary = fetch_perf_data(perf_file)
        # print('Successfully read file perf_data/' + perf_file)
        # print('\nValue of old_perf_summary is:')
        # pprint.pp(old_perf_summary)
    except:
        print('Not successful in finding file perf_data/' +
              perf_file + '; so creating it')
        old_perf_summary = {}
        write_perf_data(old_perf_summary, perf_file)

    # structure of perf_summary
    #    query_name : index_descrip : perf_profile

    # print('\nValue of new_perf_summary is:')
    # pprint.pp(new_perf_summary)

    for q_name in new_perf_summary:
        print('\ninside deeper merge')
        print(q_name)
        if q_name in old_perf_summary:
            for i_key in new_perf_summary[q_name]:
                print('inside the i_key loop:')
                print(i_key)
                # in this case, clobber old value for i_key with new value for i_key
                old_perf_summary[q_name][i_key] = new_perf_summary[q_name][i_key]
        else:
            old_perf_summary[q_name] = new_perf_summary[q_name]

    write_perf_data(old_perf_summary, perf_file)
    return old_perf_summary


# =========================================
#
#  THe pattern for text queries is different
#  For now, we will use diff queries
#     (see functions build_query_reviews_no_index(word, date1, date2)
#               and  build_query_reviews_ts(word, date1, date2)
#
#
# =========================================



def run_one_text_query_without_with_ts_index_create_keys(db_eng, 
                                                         word, 
                                                         date1, 
                                                         date2, 
                                                         index_key_prefix, 
                                                         count):
    # for each set in subsets we do a run for exactly the i_specs whose counter is in the set

    q1 = build_query_word_year_no_ts_index(word, date1, date2)
    q2 = build_query_word_year_ts_index(word, date1, date2)

    # print('starting on query q1')
    perf_profile1, time_list1 = run_one_query(db_eng, q1, count)
    # print('Perf profile for no index is:')
    pprint.pp(perf_profile1)

    # print('starting on query q2')
    perf_profile2, time_list2 = run_one_query(db_eng, q2, count)
    # print('Perf profile for ts index is:')
    pprint.pp(perf_profile2)
    
    no_ts_index_key = index_key_prefix + ''
    with_ts_index_key = index_key_prefix + 'comments_tsv_in_reviews__'

    output = {}
    
    output[no_ts_index_key] = perf_profile1
    output[with_ts_index_key] = perf_profile2

    return output


def fetch_and_update_ts_perf_data_shallow_merge(perf_file, new_perf_summary):
    # fetch or create file perf_data/perf_file
    # print('\nEntering fetch_and_update_perf_data')
    try:
        old_perf_summary = fetch_perf_data(perf_file)
        # print('Successfully read file perf_data/' + perf_file)
        # print('\nValue of old_perf_summary is:')
        # pprint.pp(old_perf_summary)
    except:
        print('Not successful in finding file perf_data/' +
              perf_file + '; so creating it')
        old_perf_summary = {}
        write_perf_data(old_perf_summary, perf_file)

    # structure of perf_summary
    #    query_name : index_descriptor : perf_profile

    # print('\nValue of new_perf_summary is:')
    # pprint.pp(new_perf_summary)

    # basically, clobber old perf_profile for any query in new_perf_summary
    for q_name in new_perf_summary:
        old_perf_summary[q_name] = new_perf_summary[q_name]

    write_perf_data(old_perf_summary, perf_file)
    return old_perf_summary


# =========================================
#
#  Now working on price_range-year-search_word qqeries
# 
#  THe pattern for text queries is different
#  For now, we will use diff queries
#     (see functions build_query_reviews_no_index(word, date1, date2)
#               and  build_query_reviews_ts(word, date1, date2)
#
#
# =========================================

# vec has shape [prange, year, sword]
def q_vec_name(vec):
    return 'q' + '_' + str(vec[0]) + '_' + str(vec[1]) + '_' + str(vec[2])
    
# qvec shoudl hold [<word>,<start_date>, <end_date>]
def run_one_word_year_query_and_multi_index_specs_ts(db_eng, q_vec, all_indexes, i_spec_list, count):
    # Build set of i_specs that will be used for a series of tests
    # first, build a list of all subsets of numbers in [0..len(i_spec_list)-1]
    subsets = build_all_subsets(len(i_spec_list))
    
    # print('\nsetting up perf_dict')

    perf_dict = {}
    key = q_vec[0] + '_' + q_vec[1][0:4]
    perf_dict[key] = {}
    pprint.pp(perf_dict)

    # for each set in subsets we do a run for exactly the i_specs whose counter is in the set
    for set in subsets:
        i_spec = []
        for n in set:
            i_spec.append(i_spec_list[n])
        # print('\nNow working on the i_spec:', i_spec)

        # set up indexes according to i_spec
        set_up_indexes(db_eng, all_indexes, i_spec)
        # print('Current set of indexes in effect is:')
        indexes_in_effect = fetch_all_index_info(db_eng, i_spec_list)
        pprint.pp(indexes_in_effect, width=150)
        
        index_key_prefix = build_index_description_key(i_spec)
        profile = run_one_text_query_without_with_ts_index_create_keys(db_eng, 
                                                                       q_vec[0],
                                                                       q_vec[1],
                                                                       q_vec[2], 
                                                                       index_key_prefix,
                                                                       count)
        
        # print('profile is:')
        pprint.pp(profile)
        
        for i in profile:
            perf_dict[key][i] = profile[i]
                

    return perf_dict


# q_vec holds [<word>, <start_date>, <end_date>]
def run_word_year_multi_index_specs_ts(db_eng, q_vec, all_indexes, i_spec_list, count):
    # Build set of i_specs that will be used for a series of tests
    # first, build a list of all subsets of numbers in [0..len(i_spec_list)-1]
    subsets = build_all_subsets(len(i_spec_list))

    perf_dict = {}
    
    # for each set in subsets we do a run for exactly the i_specs whose counter is in the set
    for set in subsets:
        i_specs = []
        for n in set:
            i_specs.append(i_spec_list[n])
        print('\nNow working on the i_specs:', i_specs)

        # set up indexes according to i_spec
        set_up_indexes(db_eng, all_indexes, i_specs)
        print('Current set of indexes in effect is:')
        indexes_in_effect = fetch_all_index_info(db_eng, all_indexes)
        pprint.pp(indexes_in_effect, width=150)
        
        q_with_ts_index = build_query_word_year_ts_index(q_vec, True)
        q_no_ts_index = build_query_word_year_no_ts_index(q_vec, False)

        print('Will be running these queries:')
        print(q_with_ts_index)
        print()
        print(q_no_ts_index)

        # run tests on query q_name, q for this index set up
        print('\nNow invoking run_one_query on the two queries')
        perf_profile_ts_index, time_listing = run_one_query(db_eng, q_with_ts_index, count)
        perf_profile_no_ts_index, time_listing = run_one_query(db_eng, q_no_ts_index, count)

        i_specs_key = build_index_description_key(i_specs)

        perf_dict[i_specs_key] = perf_profile
        
    return perf_dict



# qvec should hold list [ <price_range>, <year>, <word>]
def run_one_price_ts_query_and_multi_index_specs_with_ts(db_eng, q_vec, all_indexes, i_spec_list, count):
    # Build set of i_specs that will be used for a series of tests
    # first, build a list of all subsets of numbers in [0..len(i_spec_list)-1]
    subsets = build_all_subsets(len(i_spec_list))

    perf_dict = {}

    # for each set in subsets we do a run for exactly the i_specs whose counter is in the set
    for set in subsets:
        i_spec = []
        for n in set:
            i_spec.append(i_spec_list[n])
        print('\nNow working on the i_spec:', i_spec)

        # set up indexes according to i_spec
        set_up_indexes(db_eng, all_indexes, i_spec)
        print('Current set of indexes in effect is:')
        indexes_in_effect = fetch_all_index_info(db_eng, i_spec_list)
        pprint.pp(indexes_in_effect, width=150)
        
        q_with_ts_index = build_price_range_year_word(q_vec, True)
        q_no_ts_index = build_price_range_year_word(q_vec, False)

        # run tests on query q_name, q for this index set up
        print('\nNow invoking run_one_query with ts index')
        perf_profile_with_ts_index, time_listing = run_one_query(db_eng, q_with_ts_index, count)

        i_spec_key_with_ts_index = build_index_description_key_with_ts_index(i_spec)

        perf_dict[i_spec_key_with_ts_index] = perf_profile_with_ts_index
        
        print('\nNow invoking run_one_query no ts index')
        perf_profile_no_ts_index, time_listing = run_one_query(db_eng, q_no_ts_index, count)

        i_spec_key_no_ts_index = build_index_description_key_no_ts_index(i_spec)

        perf_dict[i_spec_key_no_ts_index] = perf_profile_no_ts_index
        

    return perf_dict

def run_prange_year_sword_and_multi_index_specs_with_ts(db_eng, q_vec, all_indexes, i_spec_list, count):
    # Build set of i_specs that will be used for a series of tests
    # first, build a list of all subsets of numbers in [0..len(i_spec_list)-1]
    subsets = build_all_subsets(len(i_spec_list))

    perf_dict = {}

    # for each set in subsets we do a run for exactly the i_specs whose counter is in the set
    for set in subsets:
        i_spec = []
        for n in set:
            i_spec.append(i_spec_list[n])
        print('\nNow working on the i_spec:', i_spec)

        # set up indexes according to i_spec
        set_up_indexes(db_eng, all_indexes, i_spec)
        print('Current set of indexes in effect is:')
        indexes_in_effect = fetch_all_index_info(db_eng, i_spec_list)
        pprint.pp(indexes_in_effect, width=150)
        
        q_with_ts_index = build_price_range_year_word(q_vec, True)
        q_no_ts_index = build_price_range_year_word(q_vec, False)

        # run tests on query q_name, q for this index set up
        print('\nNow invoking run_one_query with ts index')
        perf_profile_with_ts_index, time_listing = run_one_query(db_eng, q_with_ts_index, count)

        i_spec_key_with_ts_index = build_index_description_key_with_ts_index(i_spec)

        perf_dict[i_spec_key_with_ts_index] = perf_profile_with_ts_index
        
        print('\nNow invoking run_one_query no ts index')
        perf_profile_no_ts_index, time_listing = run_one_query(db_eng, q_no_ts_index, count)

        i_spec_key_no_ts_index = build_index_description_key_no_ts_index(i_spec)

        perf_dict[i_spec_key_no_ts_index] = perf_profile_no_ts_index
        

    return perf_dict


def run_ngroup_year_sword_and_multi_index_specs_with_ts(db_eng, q_vec, all_indexes, i_spec_list, count):
    # Build set of i_specs that will be used for a series of tests
    # first, build a list of all subsets of numbers in [0..len(i_spec_list)-1]
    subsets = build_all_subsets(len(i_spec_list))

    perf_dict = {}

    # for each set in subsets we do a run for exactly the i_specs whose counter is in the set
    for set in subsets:
        i_spec = []
        for n in set:
            i_spec.append(i_spec_list[n])
        print('\nNow working on the i_spec:', i_spec)

        # set up indexes according to i_spec
        set_up_indexes(db_eng, all_indexes, i_spec)
        print('Current set of indexes in effect is:')
        indexes_in_effect = fetch_all_index_info(db_eng, all_indexes)
        pprint.pp(indexes_in_effect, width=150)
        
        q_with_ts_index = build_ngroup_year_sword(q_vec, True)
        q_no_ts_index = build_ngroup_year_sword(q_vec, False)

        # run tests on query q_name, q for this index set up
        print('\nNow invoking run_one_query with ts index')
        perf_profile_with_ts_index, time_listing = run_one_query(db_eng, q_with_ts_index, count)

        i_spec_key_with_ts_index = build_index_description_key_with_ts_index(i_spec)

        perf_dict[i_spec_key_with_ts_index] = perf_profile_with_ts_index
        
        print('\nNow invoking run_one_query no ts index')
        perf_profile_no_ts_index, time_listing = run_one_query(db_eng, q_no_ts_index, count)

        i_spec_key_no_ts_index = build_index_description_key_no_ts_index(i_spec)

        perf_dict[i_spec_key_no_ts_index] = perf_profile_no_ts_index
        

    return perf_dict




def run_one_word_year_query_without_with_ts_index(db_eng, word, date1, date2, count):

    # for each set in subsets we do a run for exactly the i_specs whose counter is in the set

    q1 = build_query_word_year_no_ts_index(word, date1, date2)
    q2 = build_query_word_year_ts_index(word, date1, date2)

    # print('starting on query q1')
    perf_profile1, time_list1 = run_one_query(db_eng, q1, count)
    # print('Perf profile for no index is:')
    pprint.pp(perf_profile1)

    # print('starting on query q2')
    perf_profile2, time_list2 = run_one_query(db_eng, q2, count)
    # print('Perf profile for ts index is:')
    pprint.pp(perf_profile2)

    output = {}
    key = word + '_' + date1[0:4]
    output[key] = {}
    output[key]['no_ts_index'] = perf_profile1
    output[key]['with_ts_index'] = perf_profile2

    return output




#####################################################
#
#  working on an update for dates
#
#####################################################

# if group is True, then the query is baseed on neighborhood group; otherwise on neighborhood
def run_neigh_update_datetimes_multi_index_specs_ts(db_eng, group, neigh, days, all_indexes, i_spec_list, count):
    # Build set of i_specs that will be used for a series of tests
    # first, build a list of all subsets of numbers in [0..len(i_spec_list)-1]
    subsets = build_all_subsets(len(i_spec_list))

    perf_dict = {}
    
    # I want to leave the reviews table unchanged after this run, 
    #   so will alternate between adding days and subtracting days
    #   This value will toggle each time I enter a new subset of indexes
    #   (and there are always an even number of subsets)
    add_days = False

    # for each set in subsets we do a run for exactly the i_specs whose counter is in the set
    for set in subsets:
        add_days = not add_days
        print('\nIn neigh_updates routine, have set add_days to:', str(add_days))
        i_specs = []
        for n in set:
            i_specs.append(i_spec_list[n])
        print('\nNow working on the i_specs:', i_specs)

        # set up indexes according to i_spec
        set_up_indexes(db_eng, all_indexes, i_specs)
        print('Current set of indexes in effect is:')
        indexes_in_effect = fetch_all_index_info(db_eng, all_indexes)
        pprint.pp(indexes_in_effect, width=150)
        
        if group:  # focus on neighborhood groups, not neighborhoods
            if add_days:
                q = build_update_ngroup_datetime_in_reviews(db_eng, neigh, days)
            else:
                neg_days = - days
                q = build_update_ngroup_datetime_in_reviews(db_eng, neigh, neg_days)
        else:
            if add_days:
                q = build_update_neigh_datetime_in_reviews(db_eng, neigh, days)
            else:
                neg_days = - days
                q = build_update_neigh_datetime_in_reviews(db_eng, neigh, neg_days)        
        print('Will be running the query:')
        print(q)

        # run tests on query q_name, q for this index set up
        print('\nNow invoking run_one_query')
        perf_profile, time_listing = run_one_query(db_eng, q, count)

        i_specs_key = build_index_description_key(i_specs)

        perf_dict[i_specs_key] = perf_profile
        
    return perf_dict





