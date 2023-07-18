import geopy.distance

import json
import Levenshtein as lv
import pandas as pd
import pickle
import re

import requests
import sys
import traceback

from IPython.display import display
from tqdm import tqdm_notebook

class GC_Val:
    def __init__(self, data, neighborhoods):
        self.df = pd.read_csv(data)
        with open(neighborhoods, "rb") as f:
            self.neighborhoods = pickle.load(f)
            f.close()

    def get_addresses(self, ind: int) -> tuple:
        given = json.loads(str(self.df.iloc[ind].requested_address))
        response = json.loads(str(self.df.iloc[ind].response))
        resp, confidence = self.get_info(response)   
        self.format_address(given)
        self.format_address(resp)
        return (given, resp)

    def get_resources(self, response: dict) -> dict:
        return dict(dict(response['resourceSets'][0])['resources'][0])

    def get_info(self, response: dict) -> tuple:
        resources = self.get_resources(response)
        address = dict(resources['address'])
        confidence = resources['confidence']
        return (address, confidence)

    def sformat_addr(self, add: str) -> str: 
        target = ['road', 'drive', 'street', r'\.', 'saint', 'lane', 'beach', 'avenue', r'east\s?', r"west\s?", r'north\s?', r'south\s?', r'northeast\s?', r'northwest\s?',\
                  r'southeast\s?', r'southwest\s?', 'highway', 'boulevard']
        repl = ['rd', 'dr', 'st', '', 'st', 'ln', 'bc', 'ave', 'E ', 'W ', 'N ', 'S ', 'NE ', 'NW ', 'SE ', 'SW ', 'hwy', 'blvd']
        for t, r in zip(target, repl):
            add = re.sub(t, r, add)
        return add
                #   .replace('road', 'rd').replace('drive', 'dr').replace('street', 'st').replace('.', '').replace('saint', 'st').replace("lane", 'ln').replace("beach", "bc")\
                #   .replace("avenue", "ave").replace('east', 'E').replace('west', 'W').replace('north', 'N').replace('south', 'S').replace('northeast', 'NE')\
                #   .replace('northwest', 'NW').replace('southeast', 'SE').replace('southwest', 'SW').replace('highway', 'hwy').replace('boulevard', 'blvd')

    def format_entry(self, given: dict, resp: dict):
        self.format_address(given)
        self.format_address(resp)
        if 'locality' not in set(given.keys()).symmetric_difference(resp.keys()):
            if given['locality'] in resp['locality']:
                given['locality'] = resp['locality']
            elif resp['locality'] in given['locality']:
                given['locality'] = resp['locality']

    def format_address(self, add: dict):
        for key in add:
            if type(add[key]) == type([]):
                add[key] = self.sformat_addr(str(add[key][0]).lower())
            else:
                add[key] = self.sformat_addr(str(add[key]).lower())
            if key == 'postalCode':
                if type(add['postalCode']) == type(''):
                    while len(add[key]) < 5:
                        add[key] = "0" + add[key]
        return add

    def get_confidence(self, ind: int) -> str:
        response = json.loads(str(self.df.iloc[ind].response))
        address, confidence = self.get_info(response)
        return confidence
    
    def get_calculation_method(self, ind: int) -> str:
        response = self.df.iloc[ind].response
        if type(response) == str:
            return json.loads(response)['resourceSets'][0]['resources'][0]['geocodePoints'][0]['calculationMethod']
        return -1
    
    def view_entry(self, ind: int):
        print("Index:", ind)
        address = json.loads(str(self.df.iloc[ind].requested_address))
        display(address)
        response = json.loads(str(self.df.iloc[ind].response))
        address, confidence = self.get_info(response)
        display(address)
        display(confidence)
        
    def has_addressLine(self, ind: int):
        address = json.loads(self.df.iloc[ind].requested_address)
        response = json.loads(self.df.iloc[ind].response)
        address, confidence = self.get_info(response)
        return 'addressLine' in address.keys()
            
    def same_addressLine(self, ind: int, threshold: float) -> bool:
        conf = self.get_confidence(ind)
        if conf == "High":
            threshold -= 0.1
        add1, add2 = self.get_addresses(ind)
        self.format_address(add1)
        self.format_address(add2)
        if add2['addressLine'] in add1['addressLine']:
            return True
        elif lv.ratio(add1['addressLine'], add2['addressLine']) <= threshold:
            return False
        return True

    def same_admin_district(self, ind: int) -> bool:
        try:
            add1, add2 = self.get_addresses(ind)
            self.format_address(add1)
            self.format_address(add2)
            if add1['adminDistrict'] == add2['adminDistrict']:
                return True
            return False
        except KeyError as e:
            return False

    def get_ratio(self, ind: int) -> float:
        add1, add2 = self.get_addresses(ind)
        self.format_address(add1)
        self.format_address(add2)
        return lv.ratio(add1, add2)

    def format_locality(self, loc: str):
        return loc
                #   .replace('E ', '').replace('N ', '').replace('S ', '').replace('W ', '').replace('NW ', '')\
                #   .replace('NE ', '').replace('SW ', '').replace('SE ', '')

    def get_distance(self, add1: dict, add2: dict, debug=False) -> float:
        prompt = "http://dev.virtualearth.net/REST/v1/Locations?{}&{}{}&key=Ao5VXz_UhZ6NjzIF_L57R1wetZ-1YY2h_eKpLmgS-PxjHkJ_Vw89-uYqTbSDjdHp"
        city1_resp, city2_resp = (None, None)
        counter = 0
        while (city1_resp is None or city2_resp is None) and counter <= 10:
            try:
                if city1_resp is None:
                    req = ""
                    if 'postalCode' in add1.keys():
                        req = prompt.format("postalCode=" + add1['postalCode'],\
                                            "locality=" + self.format_locality(add1['locality']),\
                                            "&adminDistrict=" + add1['adminDistrict'])
                        
                    elif 'adminDistrict2' in add1.keys():
                        req = prompt.format("locality=" + self.format_locality(add1['locality']),\
                                            "adminDistrict=" + add1['adminDistrict'], "&adminDistrict2=" + add1['adminDistrict2'])
                    else:
                        req = prompt.format("locality=" + self.format_locality(add1['locality']),\
                                            "adminDistrict=" + add1['adminDistrict'], "")
                    if debug: print("city1 req:", req)
                    city1_resp = requests.get(req).json()

                if city2_resp is None:               
                    req = ""     
                    if 'postalCode' in add2.keys():
                        req = prompt.format("postalCode=" + add2['postalCode'],\
                                            "locality=" + self.format_locality(add2['locality']),\
                                            "&adminDistrict=" + add2['adminDistrict'])
                    elif 'adminDistrict2' in add2.keys():
                        req = prompt.format("locality=" + self.format_locality(add2['locality']),\
                                            "adminDistrict=" + add2['adminDistrict'], "&adminDistrict2=" + add2['adminDistrict2'])
                    else:
                        req = prompt.format("locality=" + self.format_locality(add2['locality']),\
                                            "adminDistrict=" + add2['adminDistrict'], "")
                    if debug: print("city2 req:", req)
                    city2_resp = requests.get(req).json()

            except KeyboardInterrupt:
                print("KeyboardInterrupt. Killing program...")
                sys.exit()
            except:
                traceback.print_exc()
                print("Retrying...")
                counter += 1
                continue
        
        if 'UpHierarchy' not in city1_resp['resourceSets'][0]['resources'][0]['matchCodes'] and 'UpHierarchy' not in city2_resp['resourceSets'][0]['resources'][0]['matchCodes']:
            city1_coord = city1_resp['resourceSets'][0]['resources'][0]['point']['coordinates']
            city2_coord = city2_resp['resourceSets'][0]['resources'][0]['point']['coordinates']
        else:
            if debug: print("Ambigous geocode query")
            return -1

        if debug:
            print("Given:", city1_coord)
            print("Response:", city2_coord)
        return geopy.distance.geodesic(city1_coord, city2_coord).km

    def match_postal(self, add1: dict, add2: dict) -> bool:
        postal_match = False
        try:
            postal_match = add1['postalCode'] == add2['postalCode']
        except:
            pass
        return postal_match

    def check_address_line(self, add1, add2, threshold, confidence, debug=False) -> bool:
        # Check address line (return True if confidence == High)
        if confidence == "High":
            if debug: print("Returning true because of high confidence")
            return True
        ratio = lv.ratio(add1['addressLine'], add2['addressLine'])
        if debug: print("Ratio:", ratio)
        if add2['addressLine'] in add1['addressLine']:
                if debug:
                    print("Response address line is in given address line")
                pass
        elif ratio < threshold:
            if debug: print("Wrong address line.")
            return False
        return True

    def compare_addresses(self, add1: dict, add2: dict, debug=False, threshold=0.8, max_dist=2, confidence="Medium") -> bool:
        # Go through an address line check
        # Go through a state check
        # Go through a geocode locality check
        try:
            # Address Line check
            if not ('addressLine' in add2.keys() and 'addressLine' in add1.keys()):
                if debug: print("Missing address line")
                return False
            
            if add1['adminDistrict'] == "":
                postal_match = self.match_postal(add1, add2)
                if postal_match:
                    return self.check_address_line(add1, add2, threshold=threshold, confidence=confidence, debug=debug)

            # State check
            if add1['adminDistrict'] != add2['adminDistrict']:
                if debug: print("Different adminDistrict")
                return False

            # Geocoordinate check (only if their postalCodes do not match)
            postal_match = self.match_postal(add1, add2)

            if not postal_match:
                # If confidence is high, then increase max dist by 15 km
                if confidence == "High":
                    max_dist += 15

                if add1['locality'] == add2['locality'] and add1['adminDistrict'] == add2['adminDistrict']:
                    # If it's the same city and same state
                    pass
                else:
                    distance = self.get_distance(add1, add2, debug=debug)
                    if distance == -1:
                        return self.check_address_line(add1, add2, threshold=threshold, confidence=confidence, debug=debug)
                    if debug:
                        print("Checking distances between {}, {} and {}, {}".format(add1['locality'], add1['adminDistrict'], add2['locality'], add2['adminDistrict']))
                        print("Distance:", distance)
                    if distance > max_dist:
                        try:
                            if add1['locality'] in self.neighborhoods[add1['adminDistrict']][add2['locality']]:
                                # If the user gave a neighborhood instead of a city (e.g. Encino inside Los Angeles county instead of Los Angeles)
                                if debug:
                                    print(add1['locality'] + " was found inside " + add2['locality'])
                                pass
                        except KeyError as e:
                            if debug: 
                                print("KeyError when accessing neighborhoods:", e)
                            return False
                    else:
                        if debug: print("Distance is less than threshold")
            else:
                threshold = threshold - 0.15
    
            return self.check_address_line(add1, add2, threshold=threshold, confidence=confidence, debug=debug)
        except KeyError as e:
            print("Returning false because of missing key:", e)
            return False



    def main(self, index=None, debug=False, threshold=0.8, max_dist=2, start=0, end=500, complete=False):
        if index:
            conf = self.get_confidence(index)
            given = json.loads(str(self.df.iloc[index].requested_address))
            response = json.loads(str(self.df.iloc[index].response))
            resp, confidence = self.get_info(response)
            self.format_entry(given, resp)
            if debug:
                # print("Index:", index)
                # display(given)
                # display(resp)
                self.view_entry(index)
            return self.compare_addresses(given, resp, debug=debug, threshold=threshold, max_dist=max_dist, confidence=conf)
            
        faulty = []
        no_resp = []
        if complete:
            start = 0
            end = len(self.df)
        for i in tqdm_notebook(range(start, end)):
            try:
                given = json.loads(str(self.df.iloc[i].requested_address))
                response = json.loads(str(self.df.iloc[i].response))
                resp, confidence = self.get_info(response)
            except Exception as e:
                print("Index: {}. Error: {}".format(i, e))
                print("Given address:")
                display(json.loads(str(self.df.iloc[i].requested_address)))
                print("Response address:")
                display(self.df.iloc[i].response)
                no_resp.append(i)
                continue
            self.format_entry(given, resp)
            try:
                conf = self.get_confidence(i)
                if not (value:= self.compare_addresses(given, resp, debug=debug, threshold=threshold, max_dist=max_dist, confidence=conf)): 
                    faulty.append(i)
                    if debug:
                        print("Index:", i)
                        display(given)
                        display(resp)
            except ValueError as e:
                print("Index: {}. ValueError: {}".format(i, e))
                
        return (faulty, no_resp)