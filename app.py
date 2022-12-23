import streamlit as st

st.title('Welcome to Weather Expert - a Nexus Forcasting System')
st.subheader('Please enter the following information')
zip = st.number_input('Enter your zipcode:',0,10000000000,1)
num_of_panels = st.number_input('Enter how many solar panels you have:',0,10000000000,1)
user_supplied_battery_size = st.number_input('Enter your battery size in kWh:',0,10000000000,1)
battery_percent_input = st.slider('Enter your current battery percentage:',min_value=0,max_value=100)
running = st.button('Run Program')

import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime, timedelta
import ipywidgets as widgets
import requests, json
from solarpy import irradiance_on_plane, solar_panel
from datetime import datetime
import pgeocode
from datetime import datetime
from shapely.geometry import Point
import calfire_wildfires
import numpy as np
import pandas as pd

path = "https://github.com/jrt560/data/raw/main/supermarket.csv"
demand_data = pd.read_csv(path)

demand_data.tail()
months = []
days = []
time_of_day = []

for i in range(0,np.shape(demand_data)[0]):
  temp = demand_data['date/time'][i]
  time_of_day.append(temp.split(' ')[-1])
  temp_month = temp.split('/')[0].lstrip(' ')
  months.append(int(temp_month))
  temp_day = temp.split('/')[1][0:2]
  days.append(int(temp_day))

demand_data['month']=months
demand_data['day']=days
demand_data['time_of_day']=time_of_day
demand_data = demand_data.drop(columns = ['Unnamed: 2'])
demand_data = demand_data.drop(columns = ['Unnamed: 3'])

demand_data.head()

if running == 1:
  # converting the zip code into lat/lon coordinates for the weather API.

  nomi = pgeocode.Nominatim('us')
  zip_info = nomi.query_postal_code(zip)
  zip_lat = zip_info.latitude
  zip_lon = zip_info.longitude
  
  # Finding the local weather data for the corresponding lat/lon coordinates.

  # Enter your API key here

  api_key = "0991b1584a6c341b59012416f50ce210"
  base_url = "http://api.openweathermap.org/data/2.5/forecast?"

  complete_url = base_url + "&lat=" + str(zip_lat) + "&lon=" + str(zip_lon)  + "&appid=" + api_key 

  # get method of requests module
  # return response object
  response = requests.get(complete_url)
 
  # json method of response object
  # convert json format data into
  # python format data
  forecast_data = response.json()

  ### ASSUMPTIONS
  #1: assume battery capacity if the average daily demand
  #daily_sums = demand_data.groupby(['month','day'])['kwh'].sum()
  #battery_capacity_kW =np.mean(daily_sums)/24
  #battery_capacity_kW
  
  ### ASSUMPTIONS CONTINUED
  ### FIGURE OUT BATTERY MINIMUM LEVELS

  #2: assume battery level can dip to 50% UNLESS there is a fire detected 
  #3: now check for fire, if yes, maximize battery 

  active_fire_data = calfire_wildfires.get_active_fires()
  df_fire_data = pd.DataFrame.from_dict(active_fire_data)

  geometries = []
  names = []

  if df_fire_data.empty:
    battery_min_level = 50
  else:
    for i in range(0,np.shape(df_fire_data)[0]):
      if df_fire_data.features[i]['properties']['IsActive']=='True':
        geometries.append(Point(df_fire_data.features[i]['properties']['Longitude'],df_fire_data.features[i]['properties']['Latitude']))
        names.append(df_fire_data.features[i]['properties']['Name'])
        battery_min_level = 100

  #### GETTING DATA RANGES
  start_forecast_date = datetime.strptime(forecast_data['list'][0]['dt_txt'], '%Y-%m-%d %H:%M:%S')
  end_forecast_date = datetime.strptime(forecast_data['list'][-1]['dt_txt'], '%Y-%m-%d %H:%M:%S')
  range_all_day_times = pd.date_range(start_forecast_date,end_forecast_date,freq='1H')
  range_forecast_times = pd.date_range(start_forecast_date,end_forecast_date,freq='3H')

  ### LOOP GENERATION
  battery_level = np.round(float(user_supplied_battery_size)*(float(battery_percent_input)/100),2)

  battery_levels_out = []
  solar_power_generated = []
  estimated_demand = []
  rainfall_out = []
  cloudiness_out = []

  for i in range(0,np.shape(range_all_day_times)[0]):
    input_date = str(range_all_day_times[i])
    #this line determines which forecast to use, finds the closest date/time
    index_forecast = range_forecast_times.searchsorted(range_all_day_times[i])
    temp_forecast_data = forecast_data['list'][index_forecast]
    cloudiness = temp_forecast_data["clouds"]["all"]
    try: 
      rainfall = temp_forecast_data['rain']['3h']
    except:
      rainfall = 0
    else:
      rainfall = temp_forecast_data['rain']['3h']
    rainfall_out.append(rainfall)
    year_forecast = int(input_date[0:4])
    month_forecast = int(input_date[5:7])
    day_forecast = int(input_date[8:10])
    time_of_day_forecast = (input_date[11:])
    if time_of_day_forecast == '00:00:00':
      time_of_day_adjust = '24:00:00'
    else:
      time_of_day_adjust = time_of_day_forecast
    demand_kwh = np.round(demand_data[(demand_data['month']==month_forecast)&(demand_data['day']==day_forecast)&(demand_data['time_of_day']==time_of_day_adjust)]['kwh'].values[0],2)
    estimated_demand.append(demand_kwh)
    #demand_estimated
    panel = solar_panel(2.1, 0.2, id_name='example')  # surface, efficiency and name
    panel.set_orientation(np.array([0, 0, -1]))  # upwards
    panel.set_position(zip_lat, zip_lon, 0)  # NYC latitude, longitude, altitude
    panel.set_datetime(datetime(year_forecast, month_forecast, day_forecast, int(time_of_day_forecast[0:2]), 0))  # Christmas Day!
    one_panel_energy_W = panel.power()
    all_panels_energy_kWh_no_clouds = np.round((one_panel_energy_W*float(num_of_panels))/1000,2)
    if rainfall > 0:
      cloudiness = 100  
    cloudiness_out.append(cloudiness)
    all_panels_energy_kWh_with_clouds = np.round((all_panels_energy_kWh_no_clouds * (100-cloudiness)/100),2)
    solar_power_generated.append(all_panels_energy_kWh_with_clouds)
    estimated_new_battery_level = np.round((battery_level - demand_kwh + all_panels_energy_kWh_with_clouds),2)
    if estimated_new_battery_level < float(user_supplied_battery_size)*(battery_min_level/100): 
      battery_level = battery_level + all_panels_energy_kWh_with_clouds
      battery_level = np.min([(battery_level),float(user_supplied_battery_size)])
      battery_levels_out.append(battery_level)
    else:
      battery_level = np.min([(estimated_new_battery_level),float(user_supplied_battery_size)])
      battery_levels_out.append(battery_level)
  output_df = pd.DataFrame({'dates':range_all_day_times,'battery level': battery_levels_out,
                          'solar power generated':solar_power_generated,'estimated demand':estimated_demand,
                          'cloudiness percent': cloudiness_out,'rainfall amount':rainfall_out})
  
  from plotly.subplots import make_subplots
  import plotly.graph_objects as go

  fig = make_subplots(
      rows=2, cols=1,
      subplot_titles=("Cloudiness", "Power Generation, Battery Level, and Demand"))

  fig.add_trace(go.Scatter(x=output_df['dates'], y=output_df['cloudiness percent'], line_color='#abcae4', name='Cloudiness'),
                row=1, col=1)

  fig.add_trace(go.Scatter(x=output_df['dates'], y=output_df['battery level'], line_color='#619bcc', name='Battery Level'), 
                row=2, col=1)

  fig.add_trace(go.Scatter(x=output_df['dates'], y=output_df['solar power generated'], line_color='#316a9a', name='Solar Power Generated'),
                row=2, col=1)

  fig.add_trace(go.Scatter(x=output_df['dates'], y=output_df['estimated demand'], line_color='#193750', name='Estimated Demand'),
                row=2, col=1)


  fig.update_layout(height=800, width=750,showlegend=True,
                   )
  fig['layout']['yaxis']['title']='%'
  fig['layout']['yaxis2']['title']='kW'
  fig.show()

  st.plotly_chart(fig)













