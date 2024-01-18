#!/usr/bin/env python3
"""

This script generates an index.html file for a directory. The index.html file
contains buttons for each sub-directory in the directory. Clicking on a button
will redirect to the first HTML file in the sub-directory.

If there is only one sub-directory, the index.html file will redirect to the
first HTML file in the sub-directory.

Usage:
    python render_index_html.py <directory with .diff directories inside>
"""
import argparse
import os
from pathlib import Path

css = """
    html, body {
        height: 100%;
        margin: 0;
        display: flex;
        justify-content: center;
        align-items: center;
    }
    .button-container {
        display: flex;
        flex-direction: column;
        align-items: center;
    }
    button {
        background-color: blue;
        color: white;
        border: none;
        padding: 10px 20px;
        text-align: center;
        text-decoration: none;
        display: inline-block;
        font-size: 16px;
        margin: 4px 2px;
        cursor: pointer;
        border-radius: 8px;
    }
    button:disabled {
        background-color: grey;
    }
"""


def generate_index_html(directory, prefix):
    """
    Generate the index HTML page for a diff superdirectory.
    The diff superdirectory shall contain sub-directories, each of which
    with suffix ".diff" (e.g. "Regulator_Switching.diff").

    For diff superdirectories with only one sub-directory, the index HTML page
    will redirect to the first HTML file in the sub-directory.

    For diff superdirectories with multiple sub-directories, the index HTML page
    will contain buttons for each sub-directory. Clicking on a button will
    redirect to the first HTML file in the sub-directory.

    Args:
        directory (str): The directory path.

    Returns:
        str: The generated index HTML page.

    Raises:
        None
    """
    # Find sub-directories
    sub_dirs = [
                d for d
                in os.listdir(directory)
                if os.path.isdir(os.path.join(directory, d))
                and d.endswith(".diff")  # e.g. "Regulator_Switching.diff"
        ]
    sub_dirs.sort()

    if len(sub_dirs) == 0:
        return "<html><h1>No diff sub-directories found</h1></html>"
    if len(sub_dirs) == 1:
        # If there is only one sub-directory
        sub_dir_path = Path(directory) / sub_dirs[0]
        html_files = sorted(sub_dir_path.glob("*.html"))
        url = f'{prefix}{sub_dir_path.name}/{html_files[0].name}'
        if html_files:
            return f'''
                <html>
                    <head>
                        <meta http-equiv="refresh"content="0; URL='{url}'" />
                    </head>
                </html>
            '''
        return '<h1>No diff files found</h1>'
    else:
        # If there are multiple sub-directories
        buttons_html = ""
        for sub_dir in sub_dirs:
            sub_dir_path = Path(directory) / sub_dir
            html_files = sorted(sub_dir_path.glob("*.html"))
            if html_files:
                path = f'{prefix}{sub_dir}/{html_files[0].name}'
                buttons_html += f'''
                <button onclick="window.location.href=\'{path}\'">{sub_dir}</button><br>
                '''
            else:
                buttons_html += f'<button disabled>{sub_dir} (No HTML files)</button><br>'
        return f'''
            <html>
                <head>
                    <style>{css}</style>
                </head>
                <body>
                    <div class="button-container">
                        {buttons_html}
                    </div>
                </body>
            </html>
        '''


def main():
    parser = argparse.ArgumentParser(description="Generate index.html for a directory")
    parser.add_argument("directory", type=str, help="Directory to process")
    parser.add_argument("-p", "--link-prefix", type=str,
                        default="", help="Relative path prefix to link to")
    args = parser.parse_args()

    index_html_path = os.path.join(args.directory, "index.html")
    print(f"Generating index.html at {index_html_path}")

    index_html_content = generate_index_html(args.directory, prefix=args.link_prefix)
    with open(index_html_path, "w", encoding="utf-8") as file:
        file.write(index_html_content)


if __name__ == "__main__":
    main()
