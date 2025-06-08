import json

import pandas as pd
import numpy as np

import time
from datetime import datetime




# ============================================
#
#  Basic utilities
#
# ============================================

def hello_world():
    return 'hello world!'


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
#  file manipulation utilities
#
# ============================================

# fetches filename (which should be a json file) and returns a 
#       dict corresponding to the contents of filename
def fetch_perf_data(full_file_name):
    f = open(full_file_name)
    return json.load(f)

# writes the dictionary in dict as a json file into filename
def write_perf_data(dict, full_file_name):
    with open(full_file_name, 'w') as fp:
        json.dump(dict, fp)


# ============================================
#
#  Query building utilities
#
# ============================================

def build_query_listings_join_reviews(date1, date2):
    q = """
SELECT DISTINCT l.id, l.name
FROM listings l, reviews r 
WHERE l.id = r.listing_id
  AND r.datetime >= '{0}'
  AND r.datetime <= '{1}'
ORDER BY l.id;
"""
    return q.format(date1, date2)



# ============================================
#
#  Calculating times for a run of multiple executions of a query
#
# ============================================



def calc_time_diff_per_year(db_eng, 
                            count, 
                            q_dict):
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
            # remember to add count and timestamp in your outputs
        }

        # Add metrics according to the year
        perf_details[curr_year] = perf_profile

    return perf_details


# ============================================
#
#  Queries for loading mongodb with Listings join reviews data
#
# ============================================

# updated in 2025

# FIRST batch of queries is with LEFT JOIN!

def build_query_left_join_listingsm_reviewsm():
    q = """
select *
from listingsm l left join reviewsm r 
        on l.id = r.listing_id
"""
    return q

# with 2024 data, this query fetches data for 3313 listings, useful for testing""" 
# with 2025 data, this query fetches data for 42,135 listings, probably not useful for testing""" 

def build_query_left_join_listingsm_reviewsm_10():
    q = """
select *
from listingsm l left join reviewsm r 
        on l.id = r.listing_id
  where left(l.id,2) = '10'
-- with 2025 data, this query fetches data for 42,135 listings
"""

    return q

# in 2025, this query fetches 3,978 listings
# in 2024, this query fetches 406 listings, useful for testing

def build_query_left_join_listingsm_reviewsm_100():
    q = """select *
from listingsm l left join reviewsm r 
        on l.id = r.listing_id  
  where left(l.id,3) = '100'
-- with 2025 data, this query returens 3,978 listings, useful for testing
"""
    return q

# in 2025, this query fetches 388 listings

def build_query_left_join_listingsm_reviewsm_1000():
    q = """select *
from listings l left join reviewsm r 
        on l.id = r.listing_id  
where left(l.id,r) = '1000'
-- with 2025 data, this query returens 388 listings, useful for testing
"""
    return q

# NEXT QUERIES ARE WITH FULL JOIN
# AND DO NOT USE LISTINGSM


def build_query_full_join_listings_reviewsm_10():
    q = """select *
from listings l, reviewsm r
where l.id = r.listing_id
  and left(l.id,2) = '10'
-- in 2025, this query fetches data for 42,135 listings; perhaps not useful
-- in 2024, this query fetches data for 3313 listings, useful for testing
"""
    return q

def build_query_full_join_listings_reviewsm_100():
    q = """select *
from listings l, reviewsm r
where l.id = r.listing_id
  and left(l.id,3) = '100'
"""
    return q



def build_query_full_join_listings_reviewsm():
    q = """select *
from listings l, reviewsm r
where l.id = r.listing_id"""
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






