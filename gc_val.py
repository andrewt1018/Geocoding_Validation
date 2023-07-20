# Special imports
import geopy.distance
import Levenshtein as lv

# Common imports
import json
import pandas as pd
import pickle
import re

# System imports
import requests
import sys
import traceback

# Aesthetic imports
from IPython.display import display
from tqdm import tqdm_notebook

class GC_Val:
    """
    - A class to validate geocoding data given a csv file containing all of the 
      user-inputted addresses and all of the response calls.
    - Leverages parameters such as "Confidence", "Match codes", as well as the addresses themselves
    - Classifies each address response call as either correct or incorrect
    """
    def __init__(self, data, neighborhoods=None):
        """
        Takes in a file name 'data' and converts it into a Pandas DataFrame
        Takes in a pickle file 'neighborhoods', which contains each major city's neighborhoods, and stores it in a Pandas DataFrame
        """
        self.df = pd.read_csv(data)
        if neighborhoods:
            with open(neighborhoods, "rb") as f:
                self.neighborhoods = pickle.load(f)
                f.close()
        else:
            with open(r"C:\Users\andrew.tan\Jupyter Notebooks\Geocoding_Validation\neighborhoods.csv", "rb") as f:
                self.neighborhoods = pickle.load(f)
                f.close()

        # Regex expression for checking address lines
        self.building_check = r"""^[0-9, -]+\s+.*$"""

    def main(self, index=None, debug=False, threshold=0.8, max_dist=15, start=0, end=500, complete=False):
        """
        Main method for classifying each entry as either correct or incorrect

        :param index: specific index, default none
        :param debug: a boolean to turn on/off debugging print statements
        :param threshold: a constant that marks the boundaries of similarity when comparing address lines
        :param max_dist: a constant that marks the physical boundary when retrieving distance between given and response addresses
        :param start: specifies an index to start with
        :param end: specifies an index to end with
        :param complete: if set to true, then sets start=0 and end=length-of-dataset
        :returns: list of indexes of false responses, list of indexes with NULL/faulty entries
        :rtype: type
        """
        if index is not None:
            conf = self.get_confidence(index)
            given = json.loads(str(self.df.iloc[index].requested_address))
            response = json.loads(str(self.df.iloc[index].response))
            resp, confidence = self.get_info(response)
            self.format_entry(given, resp)
            if debug:
                print("Index:", index)
                display(given)
                display(resp)
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

    def check_address_line(self, add1, add2, threshold, confidence, debug=False) -> bool:
        # Check address line (return True if confidence == High)
        if confidence == "High":
            if debug: print("Returning true because of high confidence")
            return True
        ratio = lv.ratio(add1['addressLine'], add2['addressLine'])
        if debug: print("Ratio:", ratio)
        if add2['addressLine'] in add1['addressLine']:
                if debug: print("Response address line is in given address line")
                pass
        elif ratio < threshold:
            if debug: print("Wrong address line.")
            return False
        return True

    def compare_addresses(self, add1: dict, add2: dict, debug=False, threshold=0.8, max_dist=15, confidence="High") -> bool:
        """        
        Go through an address line check
        Go through a state check
        Go through a geocode locality check

        :param add1: given address (type: dict)
        :param add2: response address (type: dict)
        :param debug: a boolean to turn on/off debugging print statements
        :param threshold: a constant that marks the boundaries of similarity when comparing address lines
        :param max_dist: a constant that marks the physical boundary when retrieving distance between given and response addresses
        :param confidence: the confidence of a given entry, defaults to 'High'. Can be 'High', 'Medium', or 'Low'
        """

        try:
            postal_match = self.match_postal(add1, add2)

            # Address Line check
            if not ('addressLine' in add2.keys() and 'addressLine' in add1.keys()):
                if debug: print("Missing address line")
                return False
            
            if len(re.findall(self.building_check, add1['addressLine'])) == 0:
                if debug:
                    print("Given address line missing building number")
                    print("Address:", add1['addressLine'])
                return False

            if len(re.findall(self.building_check, add2['addressLine'])) == 0:
                if debug:
                    print("Response address line missing building number")
                    print("Address:", add2['addressLine'])
                return False
            

            if add1['adminDistrict'] == "":
                if postal_match:
                    return self.check_address_line(add1, add2, threshold=threshold, confidence=confidence, debug=debug)

            # State check
            if add1['adminDistrict'] != add2['adminDistrict']:
                if debug: print("Different adminDistrict")
                return False

            # Geocoordinate check (only if their postalCodes do not match)
            same_city = False
            try:
                same_city = add1['locality'] == add2['locality'] and add1['adminDistrict'] == add2['adminDistrict']
            except KeyError as e:
                pass

            if not postal_match and not same_city:
                # If confidence is high, then increase max dist by 15 km
                if confidence == "High":
                    max_dist += 15
                else:
                    distance = self.get_distance(add1, add2, debug=debug)
                    if distance == -1:
                        return self.check_address_line(add1, add2, threshold=threshold, confidence=confidence, debug=debug)
                    if debug:
                        print("Checking distances between {}, {} and {}, {}".format(add1['locality'], add1['adminDistrict'], add2['locality'], add2['adminDistrict']))
                        print("Distance:", distance, "km")
                    if distance > max_dist:
                        try:
                            if add1['locality'] in self.neighborhoods[add1['adminDistrict']][add2['locality']]:
                                # If the user gave a neighborhood instead of a city (e.g. Encino inside Los Angeles county instead of Los Angeles)
                                if debug:
                                    print(add1['locality'] + " was found inside " + add2['locality'])
                                pass
                        except KeyError as e:
                            if debug: print("KeyError when accessing neighborhoods:", e)
                            return False
                    else:
                        if debug: print("Distance is less than threshold")
            else:
                if confidence == 'High': threshold = threshold - 0.15
    
            return self.check_address_line(add1, add2, threshold=threshold, confidence=confidence, debug=debug)
        except KeyError as e:
            print("Returning false because of missing key:", e)
            return False

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

    def format_entry(self, given: dict, resp: dict):
        self.format_address(given)
        self.format_address(resp)
        if 'locality' not in set(given.keys()).symmetric_difference(resp.keys()):
            if given['locality'] in resp['locality']:
                given['locality'] = resp['locality']
            elif resp['locality'] in given['locality']:
                given['locality'] = resp['locality']

    def get_addresses(self, ind: int) -> tuple:
        given = json.loads(str(self.df.iloc[ind].requested_address))
        response = json.loads(str(self.df.iloc[ind].response))
        resp, confidence = self.get_info(response)   
        self.format_entry(given, resp)
        return (given, resp)

    def get_calculation_method(self, ind: int) -> str:
        response = self.df.iloc[ind].response
        if type(response) == str:
            return json.loads(response)['resourceSets'][0]['resources'][0]['geocodePoints'][0]['calculationMethod']
        return -1

    def get_confidence(self, ind: int) -> str:
        response = json.loads(str(self.df.iloc[ind].response))
        confidence = self.get_resources(response)['confidence']
        return confidence

    def get_coord(self, addr: dict, debug=False):
        prompt = "http://dev.virtualearth.net/REST/v1/Locations?countryRegion=US"
        for key in addr.keys():
            if key == 'countryRegion' or key == 'formattedAddress' or key == 'addressLine':
                continue
            if addr[key] != None:
                prompt += f"&{key}={addr[key]}"
        prompt += "&key=Ak4BABucyHcU1YZx6T6ngVXB2ghTI8mEuAL8APeB7OQdXh2S2pWpKfPrCE0DUD30"
        prompt = re.sub("#", "%23", prompt)
        if debug: print(f"Prompt: {prompt}")
        
        resp = None
        counter = 0
        while resp == None and counter <= 10:
            try:
                resp = requests.get(prompt).json()
                if 'UpHierarchy' not in resp['resourceSets'][0]['resources'][0]['matchCodes']:
                    return resp['resourceSets'][0]['resources'][0]['point']['coordinates']
                else:
                    return -1       
            except KeyboardInterrupt:
                print("KeyboardInterrupt. Killing program...")
                sys.exit()
            except IndexError as e:
                print("Index error")
                print("Prompt:", prompt)
            except:
                traceback.print_exc()
                print("Retrying...")
                counter += 1
                continue    
        print("Outside of loop")
        print("Prompt:", prompt)
        print("Returning -1")
        return -1     
        
       
    def get_distance(self, add1: dict, add2: dict, debug=False) -> float:
        city1_coord = self.get_coord(add1, debug=debug)
        city2_coord = self.get_coord(add2, debug=debug)
        if city1_coord == -1 or city2_coord == -1:
            if debug: print("Inaccurate geocode query")
            return -1
        if debug:
            print("Given coord:", city1_coord)
            print("Response coord:", city2_coord)
        return geopy.distance.geodesic(city1_coord, city2_coord).km

    def get_info(self, response: dict) -> tuple:
        resources = self.get_resources(response)
        address = dict(resources['address'])
        confidence = resources['confidence']
        return (address, confidence)

    def get_match_codes(self, ind: int):    
        resp = json.loads(str(self.df.iloc[ind].response))
        return resp['resourceSets'][0]['resources'][0]['matchCodes']
        
    def get_ratio(self, ind: int) -> float:
        add1, add2 = self.get_addresses(ind)
        return lv.ratio(add1['addressLine'], add2['addressLine'])

    def get_resources(self, response: dict) -> dict:
        return dict(dict(response['resourceSets'][0])['resources'][0])

    def has_addressLine(self, ind: int):
        address = json.loads(self.df.iloc[ind].requested_address)
        response = json.loads(self.df.iloc[ind].response)
        address, conf = self.get_info(response)
        return 'addressLine' in address.keys()
    
    def has_building_number(self, ind: int):
        given, resp = self.get_addresses(ind)
        if len(re.findall(self.building_check, resp['addressLine'])) == 0:
            return False
        return True

    def match_postal(self, add1: dict, add2: dict) -> bool:
        postal_match = False
        try:
            postal_match = add1['postalCode'] == add2['postalCode']
        except:
            pass
        return postal_match

    def same_addressLine(self, ind: int, threshold: float) -> bool:
        conf = self.get_confidence(ind)
        if conf == "High":
            threshold -= 0.1
        add1, add2 = self.get_addresses(ind)
        if add2['addressLine'] in add1['addressLine']:
            return True
        elif lv.ratio(add1['addressLine'], add2['addressLine']) <= threshold:
            return False
        return True

    def same_admin_district(self, ind: int) -> bool:
        try:
            add1, add2 = self.get_addresses(ind)
            if add1['adminDistrict'] == add2['adminDistrict']:
                return True
            return False
        except KeyError as e:
            return False

    def sformat_addr(self, add: str) -> str: 
        target = ['road', 'drive', 'street', r'\.', 'saint', 'lane', 'beach', 'avenue', r'east\s?', r"west\s?", r'north\s?', r'south\s?', r'northeast\s?', r'northwest\s?',\
                  r'southeast\s?', r'southwest\s?', 'highway', 'boulevard', 'parkway']
        repl = ['rd', 'dr', 'st', '', 'st', 'ln', 'bc', 'ave', 'E ', 'W ', 'N ', 'S ', 'NE ', 'NW ', 'SE ', 'SW ', 'hwy', 'blvd', 'pkwy']
        for t, r in zip(target, repl):
            add = re.sub(t, r, add)
        return add
            
    def view_entry(self, ind: int):
        print("Index:", ind)
        address = json.loads(str(self.df.iloc[ind].requested_address))
        display(address)
        response = json.loads(str(self.df.iloc[ind].response))
        address, confidence = self.get_info(response)
        display(address)
        display(confidence)