import binascii
import io
import os
from struct import *

import numpy as np
import logging

from MDTdeclaration import *

# activate the loging system at the lower level
logging.basicConfig(level=logging.INFO, format="%(asctime)s -- %(levelname)s -- %(message)s")


class MDTFile:

    class _MDTBufferedReaderDecorator(object):
        def __init__(self, file_):
            self._file = file_

        def shift_stream_position(self, shift_bytes):
            self._file.seek(shift_bytes, io.SEEK_CUR)

        def read_uint8(self):
            """Read a unsigned integer coded on 1 byte (a char)"""
            return unpack("<B", self._file.read(1))[0]

        def read_uint16(self):
            """Read a unsigned integer coded on 2 byte (a short)"""
            return unpack("<H", self._file.read(2))[0]

        def read_uint32(self):
            """Read a unsigned integer coded on 4 byte (a usual int or long int)"""
            return unpack("<I", self._file.read(4))[0]

        def read_uint64(self):
            """Read a unsigned integer coded on 8 byte (a long long)"""
            return unpack("<Q", self._file.read(8))[0]

        def read_int8(self):
            """Read a signed integer coded on 1 byte (a char)"""
            return unpack("<b", self._file.read(1))[0]

        def read_int16(self):
            """Read a signed integer coded on 2 byte (a short)"""
            return unpack("<h", self._file.read(2))[0]

        def read_int32(self):
            """Read a unsigned integer coded on 4 byte (a usual int or long int)"""
            return unpack("<i", self._file.read(4))[0]

        def read_int64(self):
            """Read a unsigned integer coded on 8 byte (a long long)"""
            return unpack("<q", self._file.read(8))[0]

        def read_char(self):
            """Read one character coded on 1 byte (a usual char)"""
            return unpack("<c", self._file.read(1))[0]

        def read_uchar(self):
            """Read a unsigned integer coded on 1 byte (a char)
                idem that read_uint8()
            """
            return int(unpack('<B', self._file.read(1))[0])

        def read_double(self):
            return float(unpack('<d', self._file.read(8))[0])

        def read_float32(self):
            """Read a signed float coded on 4 byte (a float)"""
            return float(unpack('<f', self._file.read(4))[0])

        def read_float64(self):
            """Read a signed float coded on 8 byte (au double float)"""
            return float(unpack('<d', self._file.read(8))[0])

        def __getattr__(self, attr):
            return getattr(self._file, attr)

    def __init__(self, mdt_file = None):
        self.size       = 0
        self.last_frame = 0
        self.frames     = []
        self._file      =""

        if mdt_file:
            self.load_mdt_file(mdt_file)

    def load_mdt_file(self, file):
        try:
            if isinstance(file, str):
                self._file = self._MDTBufferedReaderDecorator(open(file, mode='rb'))
            else:
                self._file = self._MDTBufferedReaderDecorator(file)

            mdt_file.__read_header(self._file)

            for frm in range(mdt_file.last_frame + 1):

                logging.info("Reading frame %d" % frm)
                frame = MDTFrame.read_frame(self._file, frm)
                self.frames.append(frame)

                # to be sure we reposition the pointer where it should be after reading the frame
                self._file.seek(frame.frm_ptr_start + frame.frm_byte_size)

        finally:
            self._file.close()

    def __read_header(self, file):
        """ Read the header of the mdt file"""
        if file_size < 34: raise Exception("The file is shorter than it's header frm_byte_size")
        # magic header
        file.shift_stream_position(4)

        # File frm_byte_size (w/o header)
        self.size = file.read_uint32()

        #  4 bytes reserved (??)
        file.shift_stream_position(4)

        # last frame
        self.last_frame = file.read_uint16()

        #  18 bytes reserved (??)
        file.shift_stream_position(18)

        # documentation specifies 32 bytes long header, but zeroth frame
        # starts at 33th byte in reality
        file.shift_stream_position(1)

        if file_size < self.size + 33:
            raise Exception("Mismatch between the actual file frm_byte_size \
                             and the frm_byte_size declared in the header")


class MDTFrame:

    def __init__(self):

        # system and file ptr stuff
        self.frm_byte_size = 0 # frm_byte_size in byte of the frame
        self.frm_ptr_start = 0 #store the pointer to the beginning of the frame
        self.__var_size    = 0  # v6 and older only */
        self.__data_field  = None #store the pointer to the data for this frame
        self.__data_size   = 0 # used in old version (apparently) the size of the data file in MDADataType
        self.__cell_size   = 0 # not sure yet...

        self.type      = None
        self.version   = (0,0)

        self.title = ""
        self.guids = ""

        # the date
        self.year  = 0
        self.month = 0
        self.day   = 0
        self.hour  = 0
        self.min   = 0
        self.sec   = 0

        # all about data
        self.data       = None
        self.metadata   = ""

        self.nb_dimensions = 0      # the number of dimension
        self.dimensions    = []     # a list of the dictionary with all the dimension
        self.dimensions_unit = ""   # the unit for the dimensions (usually x and y - should be the same)

        self.nb_mesurands  = 0      # the number of mesurand (Wikipedia: the physical quantity or property which is measured.)
        self.mesurands     = []     # a list of the dictionary with all the mesurands
        self.mesurands_unit    = "" #the unit for mesurands

        # more for 2D data, those varable are here for convenient, everything is already in dimensions and/or mesurands
        self.xn            = 0 # the number of point for the x axis
        self.yn            = 0 # the number of point for the x axis
        self.xbias         = 0 # the bias for the x axis
        self.ybias         = 0 # the bias for the y axis
        self.xreal         = 0 # physical size of the data (scale*xn)
        self.yreal         = 0 # physical size of the data (scale*yn)

    def __unit_code_for_si_code(self, code):
        """transform the binary code for unit in the mda frame to understandable unit """
        if int(code) == 0x0000000000000001:
            return MDTUnit.MDT_UNIT_NONE
        elif int(code) == 0x0000000000000101:
            return MDTUnit.MDT_UNIT_METER
        elif int(code) == 0x0000000000100001:
            return MDTUnit.MDT_UNIT_VOLT2
        elif int(code) == 0x000000fffd010200:
            return MDTUnit.MDT_UNIT_SECOND
        elif int(code) == 0x0000000001000001:
            return MDTUnit.MDT_UNIT_NONE
        else :
            return MDTUnit.MDT_UNIT_SECOND

    @staticmethod
    def read_frame(file, num=0):

        frame = MDTFrame()
        frame.__extract_header(file)

        if frame.type == MDTFrameType.MDT_FRAME_SCANNED:
            logging.warning("Frame #%d: Frame STM not implemented yet." % num)

        elif (frame.type == MDTFrameType.MDT_FRAME_SPECTROSCOPY or
                      frame.type == MDTFrameType.MDT_FRAME_CURVES):
            logging.warning("Frame #%d: MDT_FRAME_SPECTROSCOPY and MDT_FRAME_CURVES not implemented yet." % num)

        elif frame.type == MDTFrameType.MDT_FRAME_TEXT:
            logging.info("Frame %d is a text frame"%num)
            frame.__extract_text_frame(file)
            logging.info("--> Frame %s loaded"%frame.title)

        elif frame.type == MDTFrameType.MDT_FRAME_OLD_MDA:
            logging.warning("Frame #%d: Old MDA frame not supported" % num)

        elif frame.type == MDTFrameType.MDT_FRAME_MDA:
            logging.info("Frame %d is a MDA frame" % num)
            frame.__read_mda_frame(file)
            logging.info("--> Frame %s loaded" % frame.title)

        elif frame.type == MDTFrameType.MDT_FRAME_CURVES_NEW:
            logging.warning("Frame #%d: MDT_FRAME_CURVES_NEW not supported." % num)

        elif frame.type == MDTFrameType.MDT_FRAME_PALETTE:
            logging.warning("Frame #%d: Frame palette data not supported." % num)

        else:
            logging.warning("Frame #%d: unknown frame type." % num)

        return frame

    def __extract_header(self, file):
        """
        load the header of the frame, starting at 'file' current position.
        :param file: a MDTBufferedReaderDecorator object warping the mdt file to load
        """
        self.frm_ptr_start = file.tell()

        # the frm_byte_size of the frame with header
        self.frm_byte_size = file.read_uint32()

        # frame type
        self.type = file.read_uint16()


        # frame version, on the C code, there is :
        # frame->version = ((guint)p[0] << 8) + (gsize)p[1];
        # debug("Frame #%u version: %d.%d",
        #          i, frame->version/0x100, frame->version % 0x100);
        # that is not clear for me ...
        self.version = (int((int.from_bytes(file.read_char(), byteorder='little') << 8) / 256),
                          int.from_bytes(file.read_char(), byteorder='little') % 256)

        # datetime
        self.year  = file.read_uint16()
        self.month = file.read_uint16()
        self.day   = file.read_uint16()
        self.hour  = file.read_uint16()
        self.min   = file.read_uint16()
        self.sec   = file.read_uint16()

        # unsigned integer, frm_byte_size of variables (in version 6 and earlier). Not used in version 7.
        self.__var_size = file.read_uint16()

    def __extract_text_frame(self, file):
        """
        Read the title, data et xml metadata of a text frame, starting at the file current position

        I reverse engineered the format, so I clearly not sure of what I'have done :)
        basically the text frame is composed of two parts, the text (the text entered by the user)
        and the XML metadata part.

        In the text part
         - 2 byte for the text length
                Note : apparently if the text frame has more than 65535 characters, Nova-PX can write it
                in this case the length is at least on 3 bytes, but it cannot reopen it...
         - 16 0x00 bytes
         - the text encoded on 1 byte (at least for latin characters)
         - 1 byte the length of the title then 3 0x00,
                if  the title is the default one 'Text Frame' this byte is not there
                and there are only the 3 0x00
                if the title is empty (i.e. "") there is 4 0x00 before the metadata
                Note : I don't know what append if the title is mor than 256 long, so don't do that !
         - the title

        In the xml part
         - the first 2 bytes are the frm_byte_size of this part usually 580
         - two 0x00 byte
         - the XML text : the characters are utf-16 packed by 2 bytes

        After that, there are some non-zero bytes, but I don't know what there are for.
        """
        size = self.frm_byte_size - ByteSize.FRAME_HEADER_SIZE

        if size < 1:
            raise Exception("the frame frm_byte_size is smaller than the frame header frm_byte_size")

        data_len = file.read_uint16() # unpack('<H', file.read(2))[0]  # int(data_buffer[pos])

        if size < 18 + data_len + 4:  # +4 for the title length bytes and the 3 zeros
            raise Exception("the frame frm_byte_size is smaller than the data frm_byte_size")

        # we jump the 16 0x00 bytes
        file.shift_stream_position(16)

        # the main text
        self.data = file.read(data_len).decode('utf-8')

        # is there a title to this frame
        title_len = file.read_uchar()
        title_trail = unpack('<3B', file.read(3)) #TODO : do something nicer with the function peak()

        # the default title and not an empty title.
        if title_len == 0 and sum(title_trail) != 0:
            title_len = 11
        elif title_trail == 0:  # the title is empty
            file.shift_stream_position(-1)

        if size < 18 + data_len + 4 + title_len:
            raise Exception("the frame frm_byte_size is smaller than the data frm_byte_size + title frm_byte_size")

        # the title of the frame
        self.title = file.read(title_len).decode('utf-8')

        if size < 18 + data_len + 4 + title_len + 2:
            raise Exception("the frame frm_byte_size is smaller than the data frm_byte_size + title frm_byte_size + XML header")

        # we unpack the length of the metadata on 2 bytes (unit16)
        xml_len = file.read_uint16()

        if size < 18 + data_len + 4 + title_len + 2 + xml_len:
            raise Exception("the frame frm_byte_size is smaller than the data frm_byte_size + title frm_byte_size + XML data")

        # we jump the 2 0x00 byte
        file.shift_stream_position(2)

        # the characters are packed on 2 bytes (it's UTF-16)
        self.metadata = file.read(xml_len).decode('utf-16')

    def __extract_mda_calibration(self, file):
        """read the information on the different axis (x,y,z) and store the in an dictionary

        the keys are :
            unit_code   : unit code (not really used anymore, but at some point the units where store in enum)
            accuracy    : the accuracy
            bias        : the bias, useful to regenerate the x axis for example
            scale       : the scale
            min_index   : the minimum
            max_index   : the maximum (some time the ULONG_MAX)
            data_type   : the type of the data store in the MDADataType Enum
            name        : the name of the axis
            comment     : comment, in certain cas (not implemented here) there is XML metadata with the x axis
            unit        : the unit in string
            author      : the author (usually empty)
        """
        calibration = dict()

        starting_position = file.tell()

        total_len = file.read_uint32()

        struct_len = file.read_uint32()
        sp = file.tell() + struct_len

        name_len                    = file.read_uint32()
        comment_len                 = file.read_uint32()
        unit_len                    = file.read_uint32()
        calibration['unit_code']    = file.read_uint64() #si_unit
        calibration['accuracy']     = file.read_double()
        fct_id                      = file.read_uint32() # not sure what is for
        fct_pointer                 = file.read_uint32() # not sure what is for
        calibration['bias']         = file.read_double()
        calibration['scale']        = file.read_double()
        calibration['min_index']    = file.read_uint64()
        calibration['max_index']    = file.read_uint64()
        calibration['data_type']    = file.read_int32() #not an unsigned int !
        author_len                  = file.read_uint32()

        file.shift_stream_position(36)

        def extract_string(string_len):
            string_bytes = file.read(string_len)
            # in don't really know why but decode('utf-8) does't work for '°'
            return "".join(map(chr, string_bytes))


        calibration['name'] = extract_string(name_len)
        file.seek(sp) # apparently there is 36 byte after the header not used (at least here)



        calibration['comment'] = extract_string(comment_len)
        calibration['unit'] = extract_string(unit_len)
        calibration['author'] = extract_string(author_len)
        calibration['comment'] = extract_string(comment_len)

        file.seek(starting_position + total_len)

        logging.info("Calibration: " + str(calibration))
        return calibration

    def __extract_mda_2D_data(self, file):
        """Extract the data for a classical mda frame (those generated by the AFM/MFM)"""
        x_axis = self.dimensions[0]
        y_axis = self.dimensions[1]
        z_axis = self.mesurands[0]

        if y_axis['unit'] != x_axis['unit'] :
            logging.warning("Frame %s : Error : the unit for X and Y are not the same !" % self.title)

        self.dimensions_unit = x_axis['unit']
        self.mesurands_unit  = z_axis['unit']


        # data size
        self.xn = x_axis['max_index'] - x_axis['min_index'] + 1
        self.yn = y_axis['max_index'] - y_axis['min_index'] + 1

        # physical size
        self.xreal = x_axis['scale'] * (self.xn - 1)
        self.yreal = y_axis['scale'] * (self.yn - 1)

        self.xbias = x_axis['bias']
        self.ybias = y_axis['bias']

        zscale = z_axis['scale']
        zoffset =  z_axis['bias']

        total = self.xn * self.yn

        try:
            file_fct_read = {
                MDADataType.MDA_DATA_INT8 : file.read_int8,
                MDADataType.MDA_DATA_UINT8 : file.read_uint8,
                MDADataType.MDA_DATA_INT16 : file.read_int16,
                MDADataType.MDA_DATA_UINT16: file.read_uint16,
                MDADataType.MDA_DATA_INT32: file.read_int32,
                MDADataType.MDA_DATA_UINT32: file.read_uint32,
                MDADataType.MDA_DATA_INT64: file.read_int64,
                MDADataType.MDA_DATA_UINT64: file.read_uint64,
                MDADataType.MDA_DATA_FLOAT32: file.read_float32,
                MDADataType.MDA_DATA_FLOAT64: file.read_float64,
            }[z_axis['data_type']]

            data = np.empty(total)
            for i in range(total):
                data[i] = zoffset + zscale*file_fct_read()

        except KeyError as e:
            logging.warning(e)
            logging.warning('The data format in the frame %s is not supported' %self.title)

        self.data = np.reshape(data, (self.xn, self.yn))

    def __extract_mda_curve(self, file): # previously extract_mda_spectrum
        """extract the data for mda curve (also called spectrum)
        with nb_mesurands == 1 and nb_dimensions  == 1 or nb_mesurands == 2 and nb_dimensions  == 0

        Warning : do no read the special case where the x value are store in the XML metadata,
                  in this case just create an x axis with a range(length of y)
        """

        # old-like or new-like curve (see comment bellow
        if self.nb_dimensions > 0 and self.nb_mesurands > 0 :
            x_axis = self.dimensions[0]
            y_axis = self.mesurands[0]
        else :
            x_axis = self.mesurands[0]
            y_axis = self.mesurands[1]


        self.dimensions_unit = x_axis['unit']
        self.mesurands_unit = y_axis['unit']

        x_scale = x_axis['scale']
        y_scale = y_axis['scale']

        self.xbias = x_axis['bias']
        self.ybias = y_axis['bias']

        data_len = x_axis['max_index'] - x_axis['min_index']

        #    /* If res == 0, fallback to arraysize */
        if data_len == 0: data_len = self.__data_size

        # there are couple so xn == yn
        self.xn = data_len
        self.yn = data_len

        try:
            file_fct_read_x_var = {
                MDADataType.MDA_DATA_INT8 : file.read_int8,
                MDADataType.MDA_DATA_UINT8 : file.read_uint8,
                MDADataType.MDA_DATA_INT16 : file.read_int16,
                MDADataType.MDA_DATA_UINT16: file.read_uint16,
                MDADataType.MDA_DATA_INT32: file.read_int32,
                MDADataType.MDA_DATA_UINT32: file.read_uint32,
                MDADataType.MDA_DATA_INT64: file.read_int64,
                MDADataType.MDA_DATA_UINT64: file.read_uint64,
                MDADataType.MDA_DATA_FLOAT32: file.read_float32,
                MDADataType.MDA_DATA_FLOAT64: file.read_float64,
            }[x_axis['data_type']]

            file_fct_read_y_var = {
                MDADataType.MDA_DATA_INT8 : file.read_int8,
                MDADataType.MDA_DATA_UINT8 : file.read_uint8,
                MDADataType.MDA_DATA_INT16 : file.read_int16,
                MDADataType.MDA_DATA_UINT16: file.read_uint16,
                MDADataType.MDA_DATA_INT32: file.read_int32,
                MDADataType.MDA_DATA_UINT32: file.read_uint32,
                MDADataType.MDA_DATA_INT64: file.read_int64,
                MDADataType.MDA_DATA_UINT64: file.read_uint64,
                MDADataType.MDA_DATA_FLOAT32: file.read_float32,
                MDADataType.MDA_DATA_FLOAT64: file.read_float64,
            }[y_axis['data_type']]

            # we check the file pointer position, just in case
            if self.__data_field != file.tell():
                raise Exception("Error : There is a shift in the reader position")

            # For this part, everything is not clear yet. According to Gwydion code there are 2 types of
            # curve the old one (nb_mesurands == 1 and nb_dimensions  == 1) with , where the y is in the data field
            # and x is in the XML-metadata part, and the new one ( nb_mesurands == 0 and nb_dimensions  == 2) where
            # the data are stocked alternatively x-y-x-y-x-y...
            #
            # But the curve generated by my version of Nova PX (3.4.0 rev 15815) are more or less of the old type
            # (nb_mesurands == 1 and the x is not in the data field) but it is not in the XML-metadata par either.
            # So we have to regenerate the x from the other metadata (from dimensions)

            if self.nb_dimensions >0: # we test if it is old type like
                y = np.empty(data_len, dtype=float)


                for n in range(data_len):
                    y[n] = y_scale*file_fct_read_y_var()

                self.yreal = y.max() - y.min()

                if x_axis["comment"] == "" : #No XML-metadata stuff
                    x = np.empty(data_len, dtype=float)
                    self.xreal = self.xn * x_scale
                    for n in range(data_len):
                        x[n] = x_axis["bias"] + n*x_axis["scale"]


                else :
                    logging.warning("The old type of MDA curve (with the x axis stocked" +
                                " in the xml metadata are not supported.")
                    x= np.arange(data_len)

            else :
                # In the new version the data structure is xyxyxyx...
                # with x and y 2 different types of data.
                x = np.empty(data_len, dtype=float)
                y = np.empty(data_len, dtype=float)
                for n in range(data_len):
                    x[n] = x_scale*file_fct_read_x_var()
                    y[n] = y_scale*file_fct_read_y_var()


            self.data = np.array([x, y])

        except KeyError as e:
            logging.debug(e)
            logging.warning('The data type in the frame %s is not supported' %self.title)

    def __extract_scanned_data(self, file):
        """extract the data generated by the STM like device"""
        pass

    def __extract_curve_data(self, file):
        pass

    def __read_mda_frame(self, file):
        """Read the header of the frame and then call the right function to read the data"""

        #to realign at the right position later
        starting_position = file.tell()

        # the header frm_byte_size and te total frm_byte_size
        head_size = file.read_uint32() #usaly 76 bytes
        total_size = file.read_uint32()

        #read guids (even if it's not really useful)
        self.guids = [str(binascii.hexlify(bytearray(file.read(16)))), str(binascii.hexlify(bytearray(file.read(16))))]

        # skip the 4 0x00 bytes
        file.shift_stream_position(4)

        #info block
        title_size = file.read_uint32()
        xml_size = file.read_uint32()
        view_info_size = file.read_uint32()
        spec_size = file.read_uint32()
        source_info_size = file.read_uint32()
        var_size = file.read_uint32()

        #skip data offset
        file.shift_stream_position(4)

        #the data frm_byte_size, not really useful because we use the var frm_byte_size...
        data_size = file.read_uint32()


        if total_size < head_size : raise Exception("the frame frm_byte_size is smaller than the header frm_byte_size")

        # to be sure to start reading at the right place
        file.seek(starting_position + head_size)

        if title_size != 0 and (self.frm_byte_size - (file.tell() - self.frm_ptr_start)) >= title_size :
            self.title = file.read(title_size).decode('utf-8')
        else :
            self.title = ""

        if xml_size and (self.frm_byte_size - (file.tell() - self.frm_ptr_start)) >= xml_size :
            self.metadata = file.read(xml_size).decode('utf-16')

        # skip FrameSpec ViewInfo SourceInfo and vars
        file.shift_stream_position(spec_size) # I clearly don't know what is the FrameSpec...
        file.shift_stream_position(view_info_size)
        file.shift_stream_position(source_info_size)

        # after there is again a 4 bytes integer with the frm_byte_size of the data
        if var_size != file.read_uint32() :
            raise Exception("The variable frm_byte_size indicated in the header is not the same that the one put in the data")

        struct_size = file.read_uint32()
        struct_pointer = file.tell()

        self.__data_size = file.read_uint64()
        self.__cell_size = file.read_uint32()
        self.nb_dimensions = file.read_uint32()
        self.nb_mesurands = file.read_uint32()

        file.seek(struct_pointer + struct_size)

        if self.nb_dimensions != 0 :
            for i in range(self.nb_dimensions) :
                self.dimensions.append(self.__extract_mda_calibration(file))

        if self.nb_mesurands != 0:
            for i in range(self.nb_mesurands):
                self.mesurands.append(self.__extract_mda_calibration(file))

        #store the pointer to the data for this frame
        self.__data_field = file.tell()


        # extraction of the 2D color map
        if self.nb_dimensions == 2 and self.nb_mesurands == 1:
            logging.info("It's a 2D MDA frame")
            self.__extract_mda_2D_data(file)

        elif ((self.nb_dimensions == 1 and self.nb_mesurands == 1)
            or (self.nb_dimensions == 0 and self.nb_mesurands == 2)):
            logging.info("It's a 1D MDA curve frame")
            self.__extract_mda_curve(file)

            pass
        elif self.nb_dimensions == 3 and self.nb_mesurands >= 1 :
            logging.info("It's a 3D MDA 'brick' frame")
            raise Exception(" MDA-Frame/brick data not supported yet.")
            # raman images */
            # if ((brick = extract_brick(mdaframe, i+1, &n, filename))) {
            #     gwy_container_transfer(brick, data, "/", "/", FALSE);
            pass
        else :
            logging.warning(" frame %s : dim = %d mes = %d, not supported\n" %
                      (self.title, self.nb_dimensions, self.nb_mesurands))

    def print_header(self):
        """
        Print all the info load from the frame header
        (for debug purpose).
        """
        logging.debug("--------------------------------------")
        logging.debug("Frame start at byte %d" % self.frm_ptr_start)
        logging.debug("frame frm_byte_size: " + str(self.frm_byte_size) + " bytes")
        logging.debug("Frame version: " + str(self.version))
        logging.debug("Frame datetime: %d-%02d-%02d %02d:%02d:%02d" % \
               (self.year, self.month, self.day, self.hour, self.min, self.sec))
        logging.debug("frame __var_size : " + str(self.__var_size) + " -- Not use in version 7.x")
        logging.debug("Frame type : " + str(self.type) + " -- "+ str(MDTFrameType(self.type)))
        logging.debug("--------------------------------------")




if __name__ == "__main__":

    import sys, os
    path = os.path.abspath(os.path.dirname(sys.argv[0]))

    filename = [
        "test5.mdt",
        "f14h20-mica.mdt",
        "erythrocytes-aa.mdt",
        "ferrite-garnet_film.mdt",
        "graphene_2.mdt",
        "plasmid_dna-aa.mdt",
        "test_structure.mdt",
        "curve_test.mdt",
        "curve_test2.mdt",
    ]

    filename = str(path) +"/Test Files/" + filename[0]
    mdt_file = MDTFile()
    file_size = os.path.getsize(filename)

    mdt_file.load_mdt_file(filename)
    for i, frm in enumerate(mdt_file.frames):
        print(str(i) + " - " + frm.title + " - " + str(frm.type))
        print(frm.xbias,frm.ybias )

    #print(mdt_file.frames[1].data)


    #np.savetxt(str(path)+"/foo.csv", mdt_file.frames[1].data, delimiter="\t")


    # print(mdt_file.frames[0].data.T)
    #
    # import numpy as np
    # import matplotlib.pyplot as plt
    #
    #
    #
    # plt.plot(mdt_file.frames[0].data.T)
    # plt.show()

   # print(mdt_file.frames[0].data)