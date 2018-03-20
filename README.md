# James-s-EVE-Dimming-Index-JEDI
The purpose of this repository of code is to search for and characterize coronal dimming in light curves produced from the Solar Dynamics Observatory (SDO) Extreme Ultraviolet (EUV) Variability Experiment (EVE). 

## Why it matters
When coronal mass ejections (CMEs) depart the corona, they leave behind a transient void. Such a region evacuated of plasma is known as a coronal dimming and it contains information about the kinetics of the CME that produced it. The dimming can be so great in the extreme ultraviolet (EUV) that it reduces the overall energy output of the sun in particular emission lines, i.e., dimming is observable in spectral irradiance. We use the SDO/EVE data to search for and parameterize dimming. We focus our search on the 39 extracted emission lines data product. We are searching these light curves for dimming around all of the >8,500 ≥C1 solar flares in the SDO era. Our method of combining these 39 light curves to remove the flare peak results in 1,521 light curves for every solar flare. Thus, we come to a total of ~13 million light curves in which to search for dimming. The question is: which ones are sensitive to CME-induced dimming?

## Overview
### Input
The code presently uses an IDL saveset that I produced spanning the era that the EVE/MEGS-A instrument was operating, 2010-2014. You can [download it here](https://www.dropbox.com/s/gi81dh2fbkpyr6g/eve_lines_2010121-2014146%20MEGS-A%20Mission%20Bare%20Bones.sav?dl=0). That instrument observes from ~6-36 nm. MEGS-B expands the range up to 106 nm, but the cadence is not uniform: a few hours per day the instrument is exposed to sunlight but most of the time the shutter is closed to minimize long-term degradation. 

Ultimately, the input will change to use [sunpy](https://github.com/sunpy/sunpy)'s Fido to fetch the data as needed. The [code for that exists in part](https://github.com/jmason86/sunpy/tree/add_eve_level2_timeseries), but is waiting for [an issue with custom Time classes in astropy](https://github.com/astropy/astropy/issues/7092) to be resolved.

### Output
The main output of the code is a really big csv file. Each row is a different event. There are 24303 columns, which include various timestamps, flags, and the primary product: dimming depth, slope, and duration for each of the 39 emission lines and every pair permutation of those emission lines. The pairing is done to apply a flare peak removal algorithm, [light_curve_peak_match_subtract](light_curve_peak_match_subtract.py). 

Additionally, an output option is to produce plots for each step in processing in order to do some sanity checks on what the various algorithms did. There's also a final summary plot produced that shows the fitted light curve with any dimming parameters annotated.

## Program flow
The main code is the wrapper script, [generate_jedi_catalog](generate_jedi_catalog.py). That calls most of the other .py files in this repository in this order:
1. [determine_preflare_irradiance](determine_preflare_irradiance.py)
2. [light_curve_peak_match_subtract](light_curve_peak_match_subtract.py)
3. [automatic_fit_light_curve](automatic_fit_light_curve.py)
4. [determine_dimming_depth](determine_dimming_depth.py)
5. [determine_dimming_slope](determine_dimming_slope.py)
6. [determine_dimming_duration](determine_dimming_duration.py)

Of course, you can call the functions in any of these files independently, but some of them have optional inputs that are intended to come from the prior functions. The headers of each are very explicit about what is required, what defaults are applied, and what value you might want to use to override defaults (from prior functions). 

## Brief code file description
* The files with a "prototype" prefix are Jupyter notebooks that were used in the initial development of their .py counterparts. Each one loads some exmaple data at the beginning so that the algorithm can be tested in full. Note: These prototypes are not necessarily kept in sync with their .py counterparts; as bugs have been fixed and defaults changed in the .py files during normal pipeline processing, they haven't necessarily been updated in the prototype. 
* The files with an "explore" prefix are Jupyter notebooks used for some initial data exploration of the data relevant to this repository. 

Below is a brief description of each file.
* [automatic_fit_light_curve.py](automatic_fit_light_curve.py): Feed it a light curve and it will use [scikit-learn's Support Vector Machine Regression](http://scikit-learn.org/stable/modules/generated/sklearn.svm.SVR.html) (SVR) to fit the light curve and find the best fit using a validation curve (and optionally plot that curve), then (optionally plot and) return that best fit. If the best fit is too crappy (see ```minimum_score``` optional input), it will return ```np.nan```. 
* [calculate_eve_fe_line_precision.py](calculate_eve_fe_line_precision.py): Compute precision for each of the iron light curves. Ultimately this will be expanded to all 39 light curves and it is planned to be used in the future to kick off uncertainty propagation through the whole JEDI pipeline. 
* [determine_dimming_depth.py](determine_dimming_depth.py): Feed it a light curve (preferably a smooth, fitted light curve) and it will find the biggest dimming depth and it's time. It'll return ```np.nan``` if none is found. 
* [determine_dimming_duration.py](determine_dimming_duration.py): Feed it a light curve (preferably a smooth, fitted light curve) and it will find the duration of dimming (where the curve drops below 0 and rises above it again, and it will return those two times as well). It'll return ```np.nan``` if it fails. 
* [determine_dimming_slope.py](determine_dimming_slope.py): Feed it a light curve (preferably a smooth, fitted light curve) and it will find the minimum, maximum, and mean slope of dimming, and it'll also return the time range it used for slope determination. This code would like to have the dimming depth time to use as the slope end time. It'll return ```np.nan``` if it fails. 
* [determine_preflare_irradiance.py](determine_preflare_irradiance.py): Feed it a light curve and a flare time, which should be toward the "right" of the time window you're providing, and it will determine the pre-flare irradiance level. It divides the time window into 3-sub windows, computes medians and standard deviations for each, and does some comparisons with optional input thresholds to figure out if it can compute a pre-flare irradiance or not. If so, it'll take the mean of those 3 medians as the pre-flare irradiance. If not, it will return ```np.nan```.
* [explore_fit_all_light_curves.ipynb](explore_fit_all_light_curves.ipynb): A Jupyter notebook to explore the idea of fitting all light curves "simultaneously" with machine learning algorithms, rather than treating each one totally independently as is done in the current JEDI pipeline. 
* [explore_jedi_catalog.ipynb](explore_jedi_catalog.ipynb): A Jupyter notebook to explore the output data of the JEDI pipeline, mainly the JEDI .csv file (the JEDI catalog). Ultimately, the analysis of the JEDI catalog will be contained in a different, dedicated repository.
* [explore_plot_all_eve_lines_data.ipynb](explore_plot_all_eve_lines_data.ipynb): A Jupyter notebook to produce a single image that displays all of the EVE lines data. 