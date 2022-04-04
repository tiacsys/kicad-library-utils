#!/usr/bin/env python3

import json
import multiprocessing
import os
import shutil
import urllib.request


class Document:
    def __init__(self, url, filename):
        self.url = url
        self.filename = filename


class DocumentManager:
    ds_urls = [
        "https://www.st.com/content/st_com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus/stm32-high-performance-mcus.cxst-rs-grid.html/SC2154.technical_literature.datasheet.json",  # noqa: E501
        "https://www.st.com/content/st_com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus/stm32-mainstream-mcus.cxst-rs-grid.html/SC2155.technical_literature.datasheet.json",  # noqa: E501
        "https://www.st.com/content/st_com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus/stm32-ultra-low-power-mcus.cxst-rs-grid.html/SC2157.technical_literature.datasheet.json",  # noqa: E501
        "https://www.st.com/content/st_com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus/stm32-wireless-mcus.cxst-rs-grid.html/SC2156.technical_literature.datasheet.json",  # noqa: E501
        # 'https://www.st.com/content/st_com/en/products/microcontrollers-microprocessors/stm32-arm-cortex-mpus.cxst-rs-grid.html/SC2230.technical_literature.datasheet.json',  # noqa: E501
    ]
    hdr = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko)"
            " Chrome/23.0.1271.64 Safari/537.11"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.3",
        "Accept-Encoding": "none",
        "Accept-Language": "en-US,en;q=0.8",
        "Connection": "keep-alive",
    }

    ds_list = list()

    _data_document_dir = "stm32_datasheets/"

    def update_ds_list(self):
        tmp_ds_list = list()
        for url in self.ds_urls:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=self.hdr)
            ) as url:
                data = json.load(url)
                rows = data["rows"]
                for row in rows:
                    tmp_ds_list.append(
                        Document(
                            url="https://www.st.com" + row["localizedLinks"]["en"],
                            filename=row["localizedLinks"]["en"].split("/")[-1],
                        )
                    )
        self.ds_list = tmp_ds_list

    def download_pdf(self, d):
        os.makedirs(self._data_document_dir, exist_ok=True)
        if not os.path.isfile(self._data_document_dir + d.filename):
            print("Downloading file {} ...".format(d.url))
            with urllib.request.urlopen(
                urllib.request.Request(d.url, headers=self.hdr)
            ) as response, open(self._data_document_dir + d.filename, "wb") as out_file:
                shutil.copyfileobj(response, out_file)
        else:
            print("Document {} already exists.".format(d.filename))

    def download(self):
        with multiprocessing.Pool(10) as pool:
            pool.map(self.download_pdf, self.ds_list)


if __name__ == "__main__":
    manager = DocumentManager()
    manager.update_ds_list()
    print("Found {} datasheets:".format(len(manager.ds_list)))
    for ds in manager.ds_list:
        print(ds.filename)
    print("Downloading...")
    manager.download()
