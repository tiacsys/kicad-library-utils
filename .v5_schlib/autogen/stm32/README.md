# STM32 library generator

This script generates KiCad symbol libraries from XML files defining pins for
STM32 devices.

## Prerequisites

* XML files, taken from STM32CubeMX install (from db/mcu folder).
* Datasheet PDFs, downloaded from ST's website.  The helper tool
  `stm32_get_datasheets.py` will download all available STM32 datasheets into
  `./stm32_datasheets/`.
* [pdfminer](https://github.com/euske/pdfminer) tool.

## Running

If you have the correct XML files, just run
`./stm32_generator.py xmldir pdfdir`, where `xmldir` is a directory containing
all the necessary XML files, and `pdfdir` is a directory containing all the PDF
files (e.g. `./stm32_datasheets/`).  Make sure the XML files have the correct
format as there is no error checking.

Mining data from the pdf filestakes time, expect about 1-2 minutes per
datasheet and CPU core.
