# Geocoding Validation
## About
This project is used to validate geocoding data responses from bing's location mapping API. Given a csv file that contains data about the user-inputted address as well as the response calls from bing's api, it would sort through them and classify each response call as either correct or incorrect.  

## Files

`gc_val.py`: main file containing all of the logic, implementation, and validation class  

`extract_false_responses.ipynb`: python notebook that extracts all of the indexes of the response calls marked as incorrect into a list. Stores it into "false_responses.pkl"  

`analyze_false_responses.ipynb`: python notebook to analyze all of the false responses. Reads in a pickle file containing the indexes of all of the false responses and concludes interesting statistics from it
  
## How to run 
1. Ensure that all of the libraries inside `gc_val.py` have been downloaded and installed
2. Open up `extract_false_responses.ipynb` and run each cell sequentially
3. Open up `analyze_false_responses.ipynb` and run each cell sequentially

