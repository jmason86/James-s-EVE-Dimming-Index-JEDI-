# Standard modules
import os
import itertools
from collections import OrderedDict
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import dates
import astropy.units as u
from astropy.time import Time
import progressbar


# Custom modules
from jpm_time_conversions import yyyydoy_sod_to_datetime
from jpm_logger import JpmLogger
from jpm_number_printing import latex_float
# from get_goes_flare_events import get_goes_flare_events  # TODO: Uncomment once sunpy method implemented
from determine_preflare_irradiance import determine_preflare_irradiance
from light_curve_peak_match_subtract import light_curve_peak_match_subtract
from automatic_fit_coronal_dimming_light_curve import automatic_fit_coronal_dimming_light_curve
from determine_dimming_depth import determine_dimming_depth
from determine_dimming_slope import determine_dimming_slope
from determine_dimming_duration import determine_dimming_duration

__author__ = 'James Paul Mason'
__contact__ = 'jmason86@gmail.com'


def generate_jedi_catalog(threshold_time_prior_flare_minutes=240.0,
                          dimming_window_relative_to_flare_minutes_left=0.0,
                          dimming_window_relative_to_flare_minutes_right=240.0,
                          threshold_minimum_dimming_window_minutes=120.0,
                          output_path='/Users/jmason86/Dropbox/Research/Postdoc_NASA/Analysis/Coronal Dimming Analysis/JEDI Catalog/',
                          verbose=False):
    """Wrapper code for creating James's Extreme Ultraviolet Variability Experiment (EVE) Dimming Index (JEDI) catalog.

    Inputs:
        None.

    Optional Inputs:
        threshold_time_prior_flare_minutes [float]:             How long before a particular event does the last one need to have
                                                                occurred to be considered independent. If the previous one was too
                                                                recent, will use that event's pre-flare irradiance.
                                                                Default is 240 (4 hours).
        dimming_window_relative_to_flare_minutes_left [float]:  Defines the left side of the time window to search for dimming
                                                                relative to the GOES/XRS flare peak. Negative numbers mean
                                                                minutes prior to the flare peak. Default is 0.0.
        dimming_window_relative_to_flare_minutes_right [float]: Defines the right side of the time window to search for dimming
                                                                relative to the GOES/XRS flare peak. If another flare
                                                                occurs before this, that time will define the end of the
                                                                window instead. Default is 240 (4 hours).
        threshold_minimum_dimming_window_minutes [float]:       The smallest allowed time window in which to search for dimming.
                                                                Default is 120.
        output_path [str]:                                      Set to a path for saving the JEDI catalog table and processing
                                                                summary plots. Default is '/Users/jmason86/Dropbox/Research/Postdoc_NASA/Analysis/Coronal Dimming Analysis/JEDI Catalog/'.
        verbose [bool]:                                         Set to log the processing messages to disk and console. Default is False.

    Outputs:
        No direct return, but writes a (csv? sql table? hdf5?) to disk with the dimming paramerization results.
        Subroutines also optionally save processing plots to disk in output_path.

    Optional Outputs:
        None

    Example:
        generate_jedi_catalog(output_path='/Users/jmason86/Dropbox/Research/Postdoc_NASA/Analysis/Coronal Dimming Analysis/JEDI Catalog/',
                              verbose=True)
    """

    # Prepare the logger for verbose
    if verbose:
        logger = JpmLogger(filename='generate_jedi_catalog', path=output_path)
        logger.info("Starting JEDI processing pipeline.")

    # Get EVE level 2 extracted emission lines data
    # TODO: Replace this shortcut method with the method I'm building into sunpy
    from scipy.io.idl import readsav
    eve_readsav = readsav('/Users/jmason86/Dropbox/Research/Data/EVE/eve_lines_2010121-2014146 MEGS-A Mission Bare Bones.sav')
    if verbose:
        logger.info('Loaded EVE data')

    # Create metadata dictionary
    # TODO: Replace this shortcut method with the method I'm building into sunpy
    from sunpy.util.metadata import MetaDict
    metadata = MetaDict()
    metadata['ion'] = eve_readsav['name']
    metadata['temperature_ion_peak_formation'] = np.power(10.0, eve_readsav['logt']) * u.Kelvin
    metadata['extracted_wavelength_center'] = eve_readsav['wavelength'] * u.nm
    metadata['extracted_wavelength_min'] = metadata['extracted_wavelength_center']
    metadata['extracted_wavelength_max'] = metadata['extracted_wavelength_center']
    metadata['emission_line_blends'] = ['none', 'yay', 'poop', 'Fe vi']  # etc
    metadata['exposure_time'] = 60.0 * u.second  # These example EVE data are already binned down to 1 minute
    metadata['precision'] = ['Not implemented in prototype']
    metadata['accuracy'] = ['Not implemented in prototype']
    metadata['flags'] = ['Not implemented in prototype']
    metadata['flags_description'] = "1 = MEGS-A data is missing, 2 = MEGS-B data is missing, 4 = ESP data is missing, 8 = MEGS-P data is missing, 16 = Possible clock adjust in MEGS-A, 32 = Possible clock adjust in MEGS-B, 64 = Possible clock adjust in ESP, 128 = Possible clock adjust in MEGS-P"
    metadata['flags_spacecraft'] = ['Not implemented in prototype']
    metadata['flags_spacecraft_description'] = "0 = No obstruction, 1 = Warmup from Earth eclipse, 2 = Obstruction atmosphere penumbra, 3 = Obstruction atmosphere umbra, 4 = Obstruction penumbra of Mercury, 5 = Obstruction penumbra of Mercury, 6 = Obstruction penumbra of Venus, 7 = Obstruction umbra of Venus, 8 = Obstruction penumbra of Moon, 9 = Obstruction umbra of Moon, 10 = Obstruction penumbra of solid Earth, 11 = Obstruction umbra of solid Earth, 16 = Observatory is off-pointed by more than 1 arcmin"
    metadata['data_version'] = ['Not implemented in prototype']
    metadata['data_reprocessed_revision'] = ['Not implemented in prototype']
    metadata['filename'] = ['Not implemented in prototype']

    # Load up the actual irradiance data into a pandas DataFrame
    # TODO: Replace this shortcut method with the method I'm building into sunpy
    irradiance = eve_readsav['irradiance'].byteswap().newbyteorder()  # pandas doesn't like big endian
    irradiance[irradiance == -1] = np.nan
    wavelengths = eve_readsav['wavelength']
    wavelengths_str = []
    [wavelengths_str.append('{0:1.1f}'.format(wavelength)) for wavelength in wavelengths]
    eve_lines = pd.DataFrame(irradiance, columns=wavelengths_str)
    eve_lines.index = yyyydoy_sod_to_datetime(eve_readsav.yyyydoy, eve_readsav.sod)  # Convert EVE standard time to datetime

    # Get GOES flare events above C1 within date range corresponding to EVE data
    # flares = get_goes_flare_events(eve_lines.index[0], eve_lines.index[-1], verbose=verbose)  # TODO: The method in sunpy needs fixing, issue 2434

    # Load GOES events from IDL saveset instead of directly through sunpy
    goes_flare_events = readsav('/Users/jmason86/Dropbox/Research/Data/GOES/events/GoesEventsC1MinMegsAEra.sav')
    goes_flare_events['class'] = goes_flare_events['class'].astype(str)
    goes_flare_events['event_peak_time_human'] = goes_flare_events['event_peak_time_human'].astype(str)
    goes_flare_events['event_start_time_human'] = goes_flare_events['event_start_time_human'].astype(str)
    goes_flare_events['peak_time'] = Time(goes_flare_events['event_peak_time_jd'], format='jd', scale='utc')
    goes_flare_events['start_time'] = Time(goes_flare_events['event_start_time_jd'], format='jd', scale='utc')
    num_flares = len(goes_flare_events['class'])
    if verbose:
        logger.info('Loaded GOES flare events.')

    # Define the columns of the JEDI catalog
    jedi_row = pd.DataFrame([OrderedDict([("GOES Flare Start Time", np.nan),
                             ("GOES Flare Peak Time", np.nan),
                             ("GOES Flare Class", np.nan),
                             ("Pre-Flare Start Time", np.nan),
                             ("Pre-Flare End Time", np.nan),
                             ("Flare Interrupt", np.nan)])])
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Pre-Flare Irradiance [W/m2]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Slope Start Time'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Slope End Time'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Slope Min [%/s]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Slope Max [%/s]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Slope Mean [%/s]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Slope Uncertainty [%/s]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Depth Time'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Depth [%]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Depth Uncertainty [%]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Duration Start Time'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Duration End Time'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Duration [s]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Fitting Gamma'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=eve_lines.columns + ' Fitting Score'))

    ion_tuples = list(itertools.permutations(eve_lines.columns.values, 2))
    ion_permutations = pd.Index([' by '.join(ion_tuples[i]) for i in range(len(ion_tuples))])

    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Slope Start Time'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Slope End Time'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Slope Min [%/s]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Slope Max [%/s]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Slope Mean [%/s]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Slope Uncertainty [%/s]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Depth Time'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Depth [%]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Depth Uncertainty [%]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Duration Start Time'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Duration End Time'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Duration [s]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Correction Time Shift [s]'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Correction Scale Factor'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Fitting Gamma'))
    jedi_row = jedi_row.join(pd.DataFrame(columns=ion_permutations + ' Fitting Score'))

    csv_filename = output_path + 'jedi_{0}.csv'.format(Time.now().iso)
    jedi_row.to_csv(csv_filename, header=True, mode='w')

    if verbose:
        logger.info('Created JEDI row definition.')

    # Start a progress bar
    widgets = [progressbar.Percentage(), progressbar.Bar(), progressbar.Timer(), ' ', progressbar.AdaptiveETA()]
    progress_bar = progressbar.ProgressBar(widgets=widgets, max_value=num_flares).start()

    # Prepare a hold-over pre-flare irradiance value,
    # which will normally have one element for each of the 39 emission lines
    preflare_irradiance = None

    # Start loop through all flares
    for flare_index in range(num_flares):

        # Skip event 0 to avoid problems with referring to earlier indices
        if flare_index == 0:
            continue

        # Reset the flare interrupt flag
        flare_interrupt = False

        # Fill the GOES flare information into the JEDI row
        jedi_row['GOES Flare Start Time'] = goes_flare_events['start_time'][flare_index].iso
        jedi_row['GOES Flare Peak Time'] = goes_flare_events['peak_time'][flare_index].iso
        jedi_row['GOES Flare Class'] = goes_flare_events['class'][flare_index]
        if verbose:
            logger.info("Event {0} GOES flare details stored to JEDI row.".format(flare_index))

        # Determine pre-flare irradiance
        minutes_since_last_flare = (goes_flare_events['peak_time'][flare_index] - goes_flare_events['peak_time'][flare_index - 1]).sec / 60.0
        if minutes_since_last_flare > threshold_time_prior_flare_minutes:
            # Clip EVE data from threshold_time_prior_flare_minutes prior to flare up to peak flare time
            preflare_window_start = (goes_flare_events['peak_time'][flare_index] - (threshold_time_prior_flare_minutes * u.minute)).iso
            preflare_window_end = (goes_flare_events['peak_time'][flare_index]).iso
            eve_lines_preflare_time = eve_lines[preflare_window_start:preflare_window_end]

            # Loop through the emission lines and get pre-flare irradiance for each
            preflare_irradiance = []
            for column in eve_lines_preflare_time:
                eve_line_preflare_time = pd.DataFrame(eve_lines_preflare_time[column])
                eve_line_preflare_time.columns = ['irradiance']
                preflare_irradiance.append(determine_preflare_irradiance(eve_line_preflare_time,
                                                                         pd.Timestamp(goes_flare_events['start_time'][flare_index].iso),
                                                                         verbose=verbose))
                plt.close('all')
        else:
            logger.info("This flare at {0} will use the pre-flare irradiance from flare at {1}."
                        .format(goes_flare_events['peak_time'][flare_index].iso,
                                goes_flare_events['peak_time'][flare_index - 1].iso))

        jedi_row["Pre-Flare Start Time"] = preflare_window_start
        jedi_row["Pre-Flare End Time"] = preflare_window_end
        preflare_irradiance_cols = [col for col in jedi_row.columns if 'Pre-Flare Irradiance' in col]
        jedi_row[preflare_irradiance_cols] = preflare_irradiance

        if verbose:
            logger.info("Event {0} pre-flare determination complete.".format(flare_index))

        # Clip EVE data to dimming window
        bracket_time_left = (goes_flare_events['peak_time'][flare_index] - (dimming_window_relative_to_flare_minutes_left * u.minute))
        next_flare_time = (goes_flare_events['peak_time'][flare_index + 1]).iso
        user_choice_time = (goes_flare_events['peak_time'][flare_index] + (dimming_window_relative_to_flare_minutes_right * u.minute))
        bracket_time_right = min(next_flare_time, user_choice_time)

        # If flare is shortening the window, set the flare_interrupt flag
        if bracket_time_right == next_flare_time:
            flare_interrupt = True
            if verbose:
                logger.info('Flare interrupt for event at {0} by flare at {1}'.format(goes_flare_events['peak_time'][flare_index].iso, next_flare_time))

        # Write flare_interrupt to JEDI row
        jedi_row['Flare Interrupt'] = flare_interrupt

        # Skip event if the dimming window is too short
        if ((bracket_time_right - bracket_time_left).sec / 60.0) < threshold_minimum_dimming_window_minutes:
            # Leave all dimming parameters as NaN and write this null result to the CSV on disk
            jedi_row.to_csv(csv_filename, header=False, mode='a')

            # Log message
            if verbose:
                logger.info('The dimming window duration of {0} minutes is shorter than the minimum threshold of {1} minutes. Skipping this event ({2})'
                            .format(((bracket_time_right - bracket_time_left).sec / 60.0), threshold_minimum_dimming_window_minutes, goes_flare_events['peak_time'][flare_index]))

            # Skip the rest of the processing in the flare_index loop
            continue
        else:
            eve_lines_event = eve_lines[bracket_time_left.iso:bracket_time_right.iso]

        if verbose:
            logger.info("Event {0} EVE data clipped to dimming window.".format(flare_index))

        # Convert irradiance units to percent
        # (in place, don't care about absolute units from this point forward)
        eve_lines_event = (eve_lines_event - preflare_irradiance) / preflare_irradiance * 100.0
        if verbose:
            logger.info("Event {0} irradiance converted from absolute to percent units.".format(flare_index))

        # Do flare removal in the light curves and add the results to the DataFrame
        for i in range(len(ion_tuples)):
            light_curve_to_subtract_from_df = pd.DataFrame(eve_lines_event[ion_tuples[i][0]])
            light_curve_to_subtract_from_df.columns = ['irradiance']
            light_curve_to_subtract_with_df = pd.DataFrame(eve_lines_event[ion_tuples[i][1]])
            light_curve_to_subtract_with_df.columns = ['irradiance']

            if (light_curve_to_subtract_from_df.isnull().all().all()) or (light_curve_to_subtract_with_df.isnull().all().all()):
                if verbose:
                    logger.info('Event {0} {1} correction skipped because all irradiances are NaN.'.format(flare_index, ion_permutations[i]))
            else:
                light_curve_corrected, seconds_shift, scale_factor = light_curve_peak_match_subtract(light_curve_to_subtract_from_df,
                                                                                                     light_curve_to_subtract_with_df,
                                                                                                     pd.Timestamp((goes_flare_events['peak_time'][flare_index]).iso),
                                                                                                     plot_path_filename=output_path + 'Peak Subtractions/Event {0} {1}.png'.format(flare_index, ion_permutations[i]),
                                                                                                     verbose=verbose)

                eve_lines_event[ion_permutations[i]] = light_curve_corrected
                jedi_row[ion_permutations[i] + ' Correction Time Shift [s]'] = seconds_shift
                jedi_row[ion_permutations[i] + ' Correction Scale Factor'] = scale_factor

                plt.close('all')

                if verbose:
                    logger.info('Event {0} flare removal correction complate'.format(flare_index))

        # TODO: Update calculate_eve_fe_line_precision to compute for all emission lines, not just selected
        uncertainty = np.ones(len(eve_lines_event)) * 0.002545

        # TODO: Propagate uncertainty through light_curve_peak_match_subtract and store in eve_lines_event

        # Fit the light curves to reduce influence of noise on the parameterizations to come later
        for column in eve_lines_event:
            if (eve_lines_event[column].isnull().all().all()):
                if verbose:
                    logger.info('Event {0} {1} fitting skipped because all irradiances are NaN.'.format(flare_index, column))
            else:
                eve_line_event = pd.DataFrame(eve_lines_event[column])
                eve_line_event.columns = ['irradiance']
                eve_line_event['uncertainty'] = uncertainty

                fitting_path = output_path + 'Fitting/'
                if not os.path.exists(fitting_path):
                    os.makedirs(fitting_path)

                plt.close('all')
                light_curve_fit, best_fit_gamma, best_fit_score = automatic_fit_coronal_dimming_light_curve(eve_line_event,
                                                                                                            plots_save_path='{0} Event {1} {2} '.format(fitting_path, flare_index, column),
                                                                                                            verbose=False)

                eve_lines_event[column] = light_curve_fit
                jedi_row[column + ' Fitting Gamma'] = best_fit_gamma
                jedi_row[column + ' Fitting Score'] = best_fit_score

                if verbose:
                    logger.info('Event {0} light curves fitted.'.format(flare_index))

        # Parameterize the light curves for dimming
        for column in eve_lines_event:
            if (eve_lines_event[column].isnull().all().all()):
                if verbose:
                    logger.info('Event {0} {1} parameterization skipped because all irradiances are NaN.'.format(flare_index, column))
            else:
                eve_line_event = pd.DataFrame(eve_lines_event[column])
                eve_line_event.columns = ['irradiance']

                # Determine dimming depth (if any)
                depth_path = output_path + 'Depth/'
                if not os.path.exists(depth_path):
                    os.makedirs(depth_path)

                plt.close('all')
                depth_percent, depth_time = determine_dimming_depth(eve_line_event,
                                                                    plot_path_filename='{0} Event {1} {2} Depth.png'.format(depth_path, flare_index, column),
                                                                    verbose=verbose)

                jedi_row[column + ' Depth [%]'] = depth_percent
                # jedi_row[column + ' Depth Uncertainty [%]'] = depth_uncertainty  # TODO: make determine_dimming_depth return the propagated uncertainty
                jedi_row[column + ' Depth Time'] = depth_time

                # Determine dimming slope (if any)
                slope_path = output_path + 'Slope/'
                if not os.path.exists(slope_path):
                    os.makedirs(slope_path)

                slope_start_time = pd.Timestamp((goes_flare_events['peak_time'][flare_index]).iso)
                slope_end_time = depth_time

                plt.close('all')
                slope_min, slope_max, slope_mean = determine_dimming_slope(eve_line_event,
                                                                           earliest_allowed_time=slope_start_time,
                                                                           latest_allowed_time=slope_end_time,
                                                                           plot_path_filename='{0} Event {1} {2} Slope.png'.format(slope_path, flare_index, column),
                                                                           verbose=verbose)

                jedi_row[column + ' Slope Min [%/s]'] = slope_min
                jedi_row[column + ' Slope Max [%/s]'] = slope_max
                jedi_row[column + ' Slope Mean [%/s]'] = slope_mean
                # jedi_row[column + ' Slope Uncertainty [%]'] = slope_uncertainty  # TODO: make determine_dimming_depth return the propagated uncertainty
                jedi_row[column + ' Slope Start Time'] = slope_start_time
                jedi_row[column + ' Slope End Time'] = slope_end_time

                # Determine dimming duration (if any)
                duration_path = output_path + 'Duration/'
                if not os.path.exists(duration_path):
                    os.makedirs(duration_path)

                plt.close('all')
                duration_seconds, duration_start_time, duration_end_time = determine_dimming_duration(eve_line_event,
                                                                                                      earliest_allowed_time=slope_start_time,
                                                                                                      plot_path_filename='{0} Event {1} {2} Duration.png'.format(duration_path, flare_index, column),
                                                                                                      verbose=verbose)

                jedi_row[column + ' Duration [s]'] = duration_seconds
                jedi_row[column + ' Duration Start Time'] = duration_start_time
                jedi_row[column + ' Duration End Time'] = duration_end_time

                if verbose:
                    logger.info("Event {0} parameterizations complete.".format(flare_index))

                # Produce a summary plot for each light curve
                plt.style.use('jpm-transparent-light')

                ax = eve_line_event['irradiance'].plot(color='black')
                plt.axhline(linestyle='dashed', color='grey')
                start_date = eve_line_event.index.values[0]
                start_date_string = pd.to_datetime(str(start_date))
                plt.xlabel(start_date_string.strftime('%Y-%m-%d %H:%M:%S'))
                plt.ylabel('Irradiance [%]')
                fmtr = dates.DateFormatter("%H:%M:%S")
                ax.xaxis.set_major_formatter(fmtr)
                ax.xaxis.set_major_locator(dates.HourLocator())
                plt.title('Event {0} {1} nm Parameters'.format(flare_index, column))

                if depth_percent:
                    plt.annotate('', xy=(depth_time, -depth_percent), xycoords='data',
                                 xytext=(depth_time, 0), textcoords='data',
                                 arrowprops=dict(facecolor='limegreen', edgecolor='limegreen', linewidth=2))
                    mid_depth = -depth_percent / 2.0
                    plt.annotate('{0:.2f} %'.format(depth_percent), xy=(depth_time, mid_depth), xycoords='data',
                                 ha='right', va='center', rotation=90, size=18, color='limegreen')

                if slope_mean:
                    p = plt.plot(eve_line_event[slope_start_time:slope_end_time]['irradiance'], c='tomato')

                    inverse_str = '$^{-1}$'
                    plt.annotate('slope_min={0} % s{1}'.format(latex_float(slope_min), inverse_str),
                                 xy=(0.98, 0.12), xycoords='axes fraction', ha='right',
                                 size=12, color=p[0].get_color())
                    plt.annotate('slope_max={0} % s{1}'.format(latex_float(slope_max), inverse_str),
                                 xy=(0.98, 0.08), xycoords='axes fraction', ha='right',
                                 size=12, color=p[0].get_color())
                    plt.annotate('slope_mean={0} % s{1}'.format(latex_float(slope_mean), inverse_str),
                                 xy=(0.98, 0.04), xycoords='axes fraction', ha='right',
                                 size=12, color=p[0].get_color())

                if duration_seconds:
                    plt.annotate('', xy=(duration_start_time, 0), xycoords='data',
                                 xytext=(duration_end_time, 0), textcoords='data',
                                 arrowprops=dict(facecolor='dodgerblue', edgecolor='dodgerblue', linewidth=5, arrowstyle='<->'))
                    mid_time = duration_start_time + (duration_end_time - duration_start_time) / 2
                    plt.annotate(str(duration_seconds) + ' s', xy=(mid_time, 0), xycoords='data', ha='center', va='bottom', size=18, color='dodgerblue')

                summary_path = output_path + 'Summary Plots/'
                if not os.path.exists(summary_path):
                    os.makedirs(summary_path)
                summary_filename = '{0} Event {1} {2} Parameter Summary.png'.format(summary_path, flare_index, column)
                plt.savefig(summary_filename)
                if verbose:
                    logger.info("Summary plot saved to %s" % summary_filename)

        # Write to the JEDI catalog on disk
        jedi_row.to_csv(csv_filename, header=False, mode='a')
        if verbose:
            logger.info('Event {0} JEDI row written to {1}.'.format(flare_index, csv_filename))

        # Update progress bar
        progress_bar.update(flare_index)