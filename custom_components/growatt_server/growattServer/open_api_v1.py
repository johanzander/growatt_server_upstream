import warnings
from datetime import date, timedelta
from . import GrowattApi
import platform
from enum import Enum
from .exceptions import GrowattParameterError, GrowattV1ApiError

class DeviceType(Enum):
    """Enumeration of Growatt device types."""
    MIX_SPH = 5  # MIX/SPH devices
    MIN_TLX = 7  # MIN/TLX devices

    @classmethod
    def get_url_prefix(cls, device_type):
        """Get the URL prefix for a given device type."""
        if device_type == cls.MIX_SPH:
            return 'mix'
        elif device_type == cls.MIN_TLX:
            return 'tlx'
        else:
            raise GrowattParameterError(f"Unsupported device type: {device_type}")



    @classmethod
    def get_url_read_param(cls, device_type):
        """Get the URL param for a given device type."""
        if device_type == cls.MIX_SPH:
            return 'readMixParam'
        elif device_type == cls.MIN_TLX:
            return 'readMinParam'
        else:
            raise GrowattParameterError(f"Unsupported device type: {device_type}")  

class ApiDataType(Enum):
    """Enumeration of Growatt device types."""
    LAST_DATA = 'last_data'
    HISTORY_DATA = 'history_data'
    BASIC_INFO = 'basic_info'
    DEVICE_SETTINGS = 'settings'
    READ_PARAM = 'read_param'


class OpenApiV1(GrowattApi):
    """
    Extended Growatt API client with V1 API support.
    This class extends the base GrowattApi class with methods for MIN/TLX and MIX/SPH inverters using
    the public V1 API described here: https://www.showdoc.com.cn/262556420217021/0
    """

    DEVICE_ENDPOINTS = {
        DeviceType.MIX_SPH: {
            # https://www.showdoc.com.cn/262556420217021/6129764434976910
            ApiDataType.LAST_DATA: 'device/mix/mix_last_data',
            # https://www.showdoc.com.cn/262556420217021/6129763571291058
            ApiDataType.BASIC_INFO: 'device/mix/mix_data_info',
            # https://www.showdoc.com.cn/262556420217021/6129765461123058
            ApiDataType.HISTORY_DATA: 'device/mix/mix_data',
            # https://www.showdoc.com.cn/262556420217021/6129763571291058
            ApiDataType.DEVICE_SETTINGS: 'device/mix/mix_data_info',
            # https://www.showdoc.com.cn/262556420217021/6129766954561259
            ApiDataType.READ_PARAM: 'readMixParam'
        },
        DeviceType.MIN_TLX: {
            # https://www.showdoc.com.cn/262556420217021/6129822090975531
            ApiDataType.LAST_DATA: 'device/tlx/tlx_last_data',
            # https://www.showdoc.com.cn/262556420217021/6129816412127075
            ApiDataType.BASIC_INFO: 'device/tlx/tlx_data_info',
            # https://www.showdoc.com.cn/262556420217021/8559849784929961
            ApiDataType.HISTORY_DATA: 'device/tlx/tlx_data',
            # https://www.showdoc.com.cn/262556420217021/8696815667375182
            ApiDataType.DEVICE_SETTINGS: 'device/tlx/tlx_set_info',
            # https://www.showdoc.com.cn/262556420217021/6129828239577315
            ApiDataType.READ_PARAM: 'readMinParam'
        }
    }

    def _create_user_agent(self):
        python_version = platform.python_version()
        system = platform.system()
        release = platform.release()
        machine = platform.machine()

        user_agent = f"Python/{python_version} ({system} {release}; {machine})"
        return user_agent

    def __init__(self, token):
        """
        Initialize the Growatt API client with V1 API support.

        Args:
            token (str): API token for authentication (required for V1 API access).
        """
        # Initialize the base class
        super().__init__(agent_identifier=self._create_user_agent())

        # Add V1 API specific properties
        self.api_url = f"{self.server_url}v1/"

        # Set up authentication for V1 API using the provided token
        self.session.headers.update({"token": token})

    def _process_response(self, response, operation_name="API operation"):
        """
        Process API response and handle errors.

        Args:
            response (dict): The JSON response from the API
            operation_name (str): Name of the operation for error messages

        Returns:
            dict: The 'data' field from the response

        Raises:
            GrowattV1ApiError: If the API returns an error response
        """
        if response.get('error_code', 1) != 0:
            raise GrowattV1ApiError(
                f"Error during {operation_name}",
                error_code=response.get('error_code'),
                error_msg=response.get('error_msg', 'Unknown error')
            )
        return response.get('data')

    def _get_url(self, page):
        """
        Simple helper function to get the page URL for v1 API.
        """
        return self.api_url + page

    def _get_device_url(self, device_type, operation):
        """Get the API URL for a specific device type and operation.
        
        Args:
            device_type (DeviceType): The type of device (MIN_TLX or MIX_SPH)
            operation (str): The operation to perform ('energy', 'settings', etc.)
            
        Returns:
            str: The complete API URL for the operation

        Raises:
            GrowattParameterError: If the device type or operation is not supported
        """
        if device_type not in self.DEVICE_ENDPOINTS:
            raise GrowattParameterError(f"Unsupported device type: {device_type}")
        if operation not in self.DEVICE_ENDPOINTS[device_type]:
            raise GrowattParameterError(f"Unsupported operation '{operation}' for device type {device_type}")
        return self.api_url + self.DEVICE_ENDPOINTS[device_type][operation]

    def plant_list(self):
        """
        Get a list of all plants with detailed information.

        Returns:
            dict: A dictionary containing plants information with 'count' and 'plants' keys.

        Raises:
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """
        # Prepare request data
        request_data = {
            'page': '',
            'perpage': '',
            'search_type': '',
            'search_keyword': ''
        }

        # Make the request
        response = self.session.get(
            url=self._get_url('plant/list'),
            data=request_data
        )

        return self._process_response(response.json(), "getting plant list")

    def plant_details(self, plant_id):
        """
        Get basic information about a power station.

        Args:
            plant_id (int): Power Station ID

        Returns:
            dict: A dictionary containing the plant details.

        Raises:
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """

        response = self.session.get(
            self._get_url('plant/details'),
            params={'plant_id': plant_id}
        )

        return self._process_response(response.json(), "getting plant details")

    def plant_energy_overview(self, plant_id):
        """
        Get an overview of a plant's energy data.

        Args:
            plant_id (int): Power Station ID

        Returns:
            dict: A dictionary containing the plant energy overview.

        Raises:
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """

        response = self.session.get(
            self._get_url('plant/data'),
            params={'plant_id': plant_id}
        )

        return self._process_response(response.json(), "getting plant energy overview")

    def plant_power_overview(self, plant_id: int, day: str | date = None) -> dict:
        """
        Obtain power data of a certain power station.
        Get the frequency once every 5 minutes

        Args:
            plant_id (int): Power Station ID
            day (date): Date - defaults to today

        Returns:
            dict: A dictionary containing the plants power data.
            .. code-block:: python

                {
                    'count': int,  # Total number of records
                    'powers': list[dict],  # List of power data entries
                    # Each entry in 'powers' is a dictionary with:
                    #   'time': str,  # Time of the power reading
                    #   'power': float | None  # Power value in Watts (can be None)
                }
        Raises:
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.

        API-Doc: https://www.showdoc.com.cn/262556420217021/1494062656174173
        """
        if day is None:
            day = date.today()

        response = self.session.get(
            self._get_url('plant/power'),
            params={
                'plant_id': plant_id,
                'date': day,
            }
        )

        return self._process_response(response.json(), "getting plant power overview")

    def plant_energy_history(self, plant_id, start_date=None, end_date=None, time_unit="day", page=None, perpage=None):
        """
        Retrieve plant energy data for multiple days/months/years.

        Args:
            plant_id (int): Power Station ID
            start_date (date, optional): Start Date - defaults to today
            end_date (date, optional): End Date - defaults to today
            time_unit (str, optional): Time unit ('day', 'month', 'year') - defaults to 'day'
            page (int, optional): Page number - defaults to 1
            perpage (int, optional): Number of items per page - defaults to 20, max 100

        Returns:
            dict: A dictionary containing the plant energy history.

        Notes:
            - When time_unit is 'day', date interval cannot exceed 7 days
            - When time_unit is 'month', start date must be within same or previous year
            - When time_unit is 'year', date interval must not exceed 20 years

        Raises:
            GrowattParameterError: If date parameters are invalid.
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """

        if start_date is None and end_date is None:
            start_date = date.today()
            end_date = date.today()
        elif start_date is None:
            start_date = end_date
        elif end_date is None:
            end_date = start_date

        # Validate date ranges based on time_unit
        if time_unit == "day" and (end_date - start_date).days > 7:
            warnings.warn(
                "Date interval must not exceed 7 days in 'day' mode.", RuntimeWarning)
        elif time_unit == "month" and (end_date.year - start_date.year > 1):
            warnings.warn(
                "Start date must be within same or previous year in 'month' mode.", RuntimeWarning)
        elif time_unit == "year" and (end_date.year - start_date.year > 20):
            warnings.warn(
                "Date interval must not exceed 20 years in 'year' mode.", RuntimeWarning)

        response = self.session.get(
            self._get_url('plant/energy'),
            params={
                'plant_id': plant_id,
                'start_date': start_date.strftime("%Y-%m-%d"),
                'end_date': end_date.strftime("%Y-%m-%d"),
                'time_unit': time_unit,
                'page': page,
                'perpage': perpage
            }
        )

        return self._process_response(response.json(), "getting plant energy history")

    def device_list(self, plant_id):
        """
        Get a list of devices in a plant. The device list includes type information that maps
        to the DeviceType enum (5 for MIX_SPH, 7 for MIN_TLX).

        Args:
            plant_id (int): The plant ID to get devices for.

        Returns:
            dict: A dictionary containing device information with 'count' and 'devices' fields.
                 Each device includes a 'type' field that maps to DeviceType enum values.

        Raises:
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """
        response = self.session.get(
            url=self._get_url('device/list'),
            params={
                'plant_id': plant_id
            }
        )

        data = self._process_response(response.json(), "getting device list")

        print(data)
        
        # Add device_type mapping for each device based on type
        if 'devices' in data:
            for device in data['devices']:
                try:
                    device_type = device.get('type')
                    if device_type:
                        device['device_type'] = DeviceType(device_type)
                except ValueError:
                    device['device_type'] = None
        return data

    def device_details(self, device_sn, device_type):
        """
        Get detailed data for a device.

        Args:
            device_sn (str): The serial number of the device.
            device_type (DeviceType): The type of device (MIN_TLX or MIX_SPH).

        Returns:
            dict: A dictionary containing the device details.

        Raises:
            GrowattParameterError: If the device type is not supported.
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """
        if not isinstance(device_type, DeviceType):
            raise GrowattParameterError(f"Invalid device type: {device_type}")

        response = self.session.get(
            self._get_device_url(device_type, ApiDataType.BASIC_INFO),
            params={
                'device_sn': device_sn
            }
        )

        return self._process_response(response.json(), f"getting {device_type.name} details")

    def device_energy(self, device_sn, device_type):
        """
        Get energy data for a device.

        Args:
            device_sn (str): The serial number of the device.
            device_type (DeviceType): The type of device (MIN_TLX or MIX_SPH).

        Returns:
            dict: A dictionary containing the device energy data.

        Raises:
            GrowattParameterError: If the device type is not supported.
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """
        if not isinstance(device_type, DeviceType):
            raise GrowattParameterError(f"Invalid device type: {device_type}")

        url_prefix = DeviceType.get_url_prefix(device_type)
        
        response = self.session.post(
            url=self._get_device_url(device_type, ApiDataType.LAST_DATA),
            data={
                f"{url_prefix}_sn": device_sn
            }
        )


        # responseHydrated = self._process_response(response.json(), f"getting {device_type.name} energy data")

        # responseHydrated['epvToday'] = responseHydrated.get('epv1Today', 0) + responseHydrated.get("epv2Today", 0)
        
        return self._process_response(response.json(), f"getting {device_type.name} energy data")
    
    def min_energy(self, device_sn):
        """
        Get energy data for a MIN inverter.             
        return self.device_energy(device_sn, DeviceType.MIN_TLX)
        Args:
            device_sn (str): The serial number of the MIN inverter.
        Returns:
            dict: A dictionary containing the MIN inverter energy data.
        Raises:
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """

        return self.device_energy(device_sn, DeviceType.MIN_TLX)

    def device_settings(self, device_sn, device_type):

        """
        Get settings for a device.

        Args:
            device_sn (str): The serial number of the device.
            device_type (DeviceType): The type of device (MIN_TLX or MIX_SPH).

        Returns:
            dict: A dictionary containing the device settings.

        Raises:
            GrowattParameterError: If the device type is not supported.
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """
        if not isinstance(device_type, DeviceType):
            raise GrowattParameterError(f"Invalid device type: {device_type}")

        response = self.session.get(
            self._get_device_url(device_type, ApiDataType.DEVICE_SETTINGS),
            params={
                'device_sn': device_sn
            }
        )

        return self._process_response(response.json(), f"getting {device_type.name} settings")
    
    def min_settings(self, device_sn):
        """
        Get settings for a MIN inverter.

        Args:
            device_sn (str): The serial number of the MIN inverter.

        Returns:
            dict: A dictionary containing the MIN inverter settings.

        Raises:
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """

        return self.device_settings(device_sn, DeviceType.MIN_TLX)

    def device_energy_history(self, device_sn, device_type, start_date=None, end_date=None, timezone=None, page=None, limit=None):
        """
        Get device energy history data.

        Args:
            device_sn (str): The ID of the device.
            device_type (DeviceType): The type of device (MIN_TLX or MIX_SPH).
            start_date (date, optional): Start date. Defaults to today.
            end_date (date, optional): End date. Defaults to today.
            timezone (str, optional): Timezone ID.
            page (int, optional): Page number.
            limit (int, optional): Results per page.

        Returns:
            dict: A dictionary containing the device history data.

        Raises:
            GrowattParameterError: If device type is invalid or date interval exceeds 7 days.
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """
        if not isinstance(device_type, DeviceType):
            raise GrowattParameterError(f"Invalid device type: {device_type}")

        if start_date is None and end_date is None:
            start_date = date.today()
            end_date = date.today()
        elif start_date is None:
            start_date = end_date
        elif end_date is None:
            end_date = start_date

        # check interval validity
        if end_date - start_date > timedelta(days=7):
            raise GrowattParameterError("date interval must not exceed 7 days")

        url_prefix = DeviceType.get_url_prefix(device_type)
        response = self.session.post(
            url=self._get_device_url(device_type, ApiDataType.HISTORY_DATA),
            data={
                f"{url_prefix}_sn": device_sn,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "timezone_id": timezone,
                "page": page,
                "perpage": limit,
            }
        )

        return self._process_response(response.json(), f"getting {device_type.name} energy history")
    
    def common_read_parameter(self, device_sn, device_type, parameter_id, start_address=None, end_address=None):
        """
        Read setting from MIN inverter.

        Args:
            device_sn (str): The ID of the TLX inverter.
            parameter_id (str): Parameter ID to read. Don't use start_address and end_address if this is set.
            start_address (int, optional): Register start address (for set_any_reg). Don't use parameter_id if this is set.
            end_address (int, optional): Register end address (for set_any_reg). Don't use parameter_id if this is set.

        Returns:
            dict: A dictionary containing the setting value.

        Raises:
            GrowattParameterError: If parameters are invalid.
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """

        if not isinstance(device_type, DeviceType):
            raise GrowattParameterError(f"Invalid device type: {device_type}")

        if parameter_id is None and start_address is None:
            raise GrowattParameterError(
                "specify either parameter_id or start_address/end_address")
        elif parameter_id is not None and start_address is not None:
            raise GrowattParameterError(
                "specify either parameter_id or start_address/end_address - not both."
            )
        elif parameter_id is not None:
            # named parameter
            start_address = 0
            end_address = 0
        else:
            # using register-number mode
            parameter_id = "set_any_reg"
            if start_address is None:
                start_address = end_address
            if end_address is None:
                end_address = start_address

        response = self.session.post(
            self._get_device_url(device_type, ApiDataType.READ_PARAM),
            data={
                "device_sn": device_sn,
                "paramId": parameter_id,
                "startAddr": start_address,
                "endAddr": end_address,
            }
        )

        return self._process_response(response.json(), f"reading parameter {parameter_id}")

    def min_write_parameter(self, device_sn, parameter_id, parameter_values=None):
        """
        Set parameters on a MIN inverter.

        Args:
            device_sn (str): Serial number of the inverter
            parameter_id (str): Setting type to be configured
            parameter_values: Parameter values to be sent to the system.
                Can be a single string (for param1 only),
                a list of strings (for sequential params),
                or a dictionary mapping param positions to values

        Returns:
            dict: JSON response from the server

        Raises:
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """

        # Initialize all parameters as empty strings
        parameters = {i: "" for i in range(1, 20)}

        # Process parameter values based on type
        if parameter_values is not None:
            if isinstance(parameter_values, (str, int, float, bool)):
                # Single value goes to param1
                parameters[1] = str(parameter_values)
            elif isinstance(parameter_values, list):
                # List of values go to sequential params
                for i, value in enumerate(parameter_values, 1):
                    if i <= 19:  # Only use up to 19 parameters
                        parameters[i] = str(value)
            elif isinstance(parameter_values, dict):
                # Dict maps param positions to values
                for pos, value in parameter_values.items():
                    pos = int(pos) if not isinstance(pos, int) else pos
                    if 1 <= pos <= 19:  # Validate parameter positions
                        parameters[pos] = str(value)

        # IMPORTANT: Create a data dictionary with ALL parameters explicitly included
        request_data = {
            "tlx_sn": device_sn,
            "type": parameter_id
        }

        # Add all 19 parameters to the request
        for i in range(1, 20):
            request_data[f"param{i}"] = str(parameters[i])

        # Send the request
        response = self.session.post(
            self._get_url('tlxSet'),
            data=request_data
        )

        return self._process_response(response.json(), f"writing parameter {parameter_id}")

    def min_write_time_segment(self, device_sn, segment_id, batt_mode, start_time, end_time, enabled=True):
        """
        Set a time segment for a MIN inverter.

        Args:
            device_sn (str): The serial number of the inverter.
            segment_id (int): Time segment ID (1-9).
            batt_mode (int): 0=load priority, 1=battery priority, 2=grid priority.
            start_time (datetime.time): Start time for the segment.
            end_time (datetime.time): End time for the segment.
            enabled (bool): Whether this segment is enabled.

        Returns:
            dict: The server response.

        Raises:
            GrowattParameterError: If parameters are invalid.
            GrowattV1ApiError: If the API returns an error response.
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """

        if not 1 <= segment_id <= 9:
            raise GrowattParameterError("segment_id must be between 1 and 9")

        if not 0 <= batt_mode <= 2:
            raise GrowattParameterError("batt_mode must be between 0 and 2")

        # Initialize ALL 19 parameters as empty strings, not just the ones we need
        all_params = {
            "tlx_sn": device_sn,
            "type": f"time_segment{segment_id}"
        }

        # Add param1 through param19, setting the values we need
        all_params["param1"] = str(batt_mode)
        all_params["param2"] = str(start_time.hour)
        all_params["param3"] = str(start_time.minute)
        all_params["param4"] = str(end_time.hour)
        all_params["param5"] = str(end_time.minute)
        all_params["param6"] = "1" if enabled else "0"

        # Add empty strings for all unused parameters
        for i in range(7, 20):
            all_params[f"param{i}"] = ""

        # Send the request
        response = self.session.post(
            self._get_url('tlxSet'),
            data=all_params
        )

        return self._process_response(response.json(), f"writing time segment {segment_id}")

    def min_read_time_segments(self, device_sn, settings_data=None):
        """
        Read Time-of-Use (TOU) settings from a Growatt MIN/TLX inverter.

        Retrieves all 9 time segments from a Growatt MIN/TLX inverter and
        parses them into a structured format.

        Note that this function uses min_settings() internally to get the settings data,
        To avoid endpoint rate limit, you can pass the settings_data parameter
        with the data returned from min_settings().

        Args:
            device_sn (str): The device serial number of the inverter
            settings_data (dict, optional): Settings data from min_settings call to avoid repeated API calls.
                                            Can be either the complete response or just the data portion.

        Returns:
            list: A list of dictionaries, each containing details for one time segment:
                - segment_id (int): The segment number (1-9)
                - batt_mode (int): 0=Load First, 1=Battery First, 2=Grid First
                - mode_name (str): String representation of the mode
                - start_time (str): Start time in format "HH:MM"
                - end_time (str): End time in format "HH:MM"
                - enabled (bool): Whether the segment is enabled

        Example:
            # Option 1: Make a single call
            tou_settings = api.min_read_time_segments("DEVICE_SERIAL_NUMBER")

            # Option 2: Reuse existing settings data
            settings_response = api.min_settings("DEVICE_SERIAL_NUMBER")
            tou_settings = api.min_read_time_segments("DEVICE_SERIAL_NUMBER", settings_response)

        Raises:
            GrowattV1ApiError: If the API request fails
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """

        # Process the settings data
        if settings_data is None:
            # Fetch settings if not provided
            settings_data = self.min_settings(device_sn=device_sn)

        # Define mode names
        mode_names = {
            0: "Load First",
            1: "Battery First",
            2: "Grid First"
        }

        segments = []

        # Process each time segment
        for i in range(1, 10):  # Segments 1-9
            # Get raw time values
            start_time_raw = settings_data.get(f'forcedTimeStart{i}', "0:0")
            end_time_raw = settings_data.get(f'forcedTimeStop{i}', "0:0")

            # Handle 'null' string values
            if start_time_raw == 'null' or not start_time_raw:
                start_time_raw = "0:0"
            if end_time_raw == 'null' or not end_time_raw:
                end_time_raw = "0:0"

            # Format times with leading zeros (HH:MM)
            try:
                start_parts = start_time_raw.split(":")
                start_hour = int(start_parts[0])
                start_min = int(start_parts[1])
                start_time = f"{start_hour:02d}:{start_min:02d}"
            except (ValueError, IndexError):
                start_time = "00:00"

            try:
                end_parts = end_time_raw.split(":")
                end_hour = int(end_parts[0])
                end_min = int(end_parts[1])
                end_time = f"{end_hour:02d}:{end_min:02d}"
            except (ValueError, IndexError):
                end_time = "00:00"

            # Get the mode value safely
            mode_raw = settings_data.get(f'time{i}Mode')
            if mode_raw == 'null' or mode_raw is None:
                batt_mode = None
            else:
                try:
                    batt_mode = int(mode_raw)
                except (ValueError, TypeError):
                    batt_mode = None

            # Get the enabled status safely
            enabled_raw = settings_data.get(f'forcedStopSwitch{i}', 0)
            if enabled_raw == 'null' or enabled_raw is None:
                enabled = False
            else:
                try:
                    enabled = int(enabled_raw) == 1
                except (ValueError, TypeError):
                    enabled = False

            segment = {
                'segment_id': i,
                'batt_mode': batt_mode,
                'mode_name': mode_names.get(batt_mode, "Unknown"),
                'start_time': start_time,
                'end_time': end_time,
                'enabled': enabled
            }

            segments.append(segment)

        return segments
    
    def read_time_segments(self, device_sn, device_type, settings_data=None):
        """
        Read Time-of-Use (TOU) settings from a Growatt MIN/TLX or MIX/SPH inverter.

        Retrieves all 9 time segments from a Growatt MIN/TLX or MIX/SPH inverter and
        parses them into a structured format.   

        Note that this function uses device_settings() internally to get the settings data,
        To avoid endpoint rate limit, you can pass the settings_data parameter
        with the data returned from device_settings().  

        Args:
            device_sn (str): The device serial number of the inverter
            device_type (DeviceType): The type of device (MIN_TLX or MIX_SPH).
            settings_data (dict, optional): Settings data from device_settings call to avoid repeated API calls.
                                            Can be either the complete response or just the data portion.
        Returns:
            list: A list of dictionaries, each containing details for one time segment:
                - segment_id (int): The segment number (1-9)
                - batt_mode (int): 0=Load First, 1=Battery First, 2=Grid First
                - mode_name (str): String representation of the mode
                - start_time (str): Start time in format "HH:MM"
                - end_time (str): End time in format "HH:MM"
                - enabled (bool): Whether the segment is enabled    
        Example:
            # Option 1: Make a single call
            tou_settings = api.read_time_segments("DEVICE_SERIAL_NUMBER", DeviceType.MIN_TLX)       
            # Option 2: Reuse existing settings data
            settings_response = api.device_settings("DEVICE_SERIAL_NUMBER", DeviceType.MIN_TLX)
            tou_settings = api.read_time_segments("DEVICE_SERIAL_NUMBER", DeviceType.MIN_TLX, settings_response)
        Raises:
            GrowattParameterError: If device type is invalid.
            GrowattV1ApiError: If the API request fails     
            requests.exceptions.RequestException: If there is an issue with the HTTP request.
        """

        # Process the settings data
        if settings_data is None:
            # Fetch settings if not provided
            settings_data = self.device_settings(device_sn, device_type=device_type)

        # Define mode names
        mode_names = {
            0: "Load First",
            1: "Battery First",
            2: "Grid First"
        }

        segments = []

        # Process each time segment
        for i in range(1, 10):  # Segments 1-9
            # Get raw time values
            start_time_raw = settings_data.get(f'forcedTimeStart{i}', "0:0")
            end_time_raw = settings_data.get(f'forcedTimeStop{i}', "0:0")

            # Handle 'null' string values
            if start_time_raw == 'null' or not start_time_raw:
                start_time_raw = "0:0"
            if end_time_raw == 'null' or not end_time_raw:
                end_time_raw = "0:0"

            # Format times with leading zeros (HH:MM)
            try:
                start_parts = start_time_raw.split(":")
                start_hour = int(start_parts[0])
                start_min = int(start_parts[1])
                start_time = f"{start_hour:02d}:{start_min:02d}"
            except (ValueError, IndexError):
                start_time = "00:00"

            try:
                end_parts = end_time_raw.split(":")
                end_hour = int(end_parts[0])
                end_min = int(end_parts[1])
                end_time = f"{end_hour:02d}:{end_min:02d}"
            except (ValueError, IndexError):
                end_time = "00:00"

            # Get the mode value safely
            mode_raw = settings_data.get(f'time{i}Mode')
            if mode_raw == 'null' or mode_raw is None:
                batt_mode = None
            else:
                try:
                    batt_mode = int(mode_raw)
                except (ValueError, TypeError):
                    batt_mode = None

            # Get the enabled status safely
            enabled_raw = settings_data.get(f'forcedStopSwitch{i}', 0)
            if enabled_raw == 'null' or enabled_raw is None:
                enabled = False
            else:
                try:
                    enabled = int(enabled_raw) == 1
                except (ValueError, TypeError):
                    enabled = False

            segment = {
                'segment_id': i,
                'batt_mode': batt_mode,
                'mode_name': mode_names.get(batt_mode, "Unknown"),
                'start_time': start_time,
                'end_time': end_time,
                'enabled': enabled
            }

            segments.append(segment)

        return segments
