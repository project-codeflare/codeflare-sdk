// Copyright 2024 IBM, Red Hat
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//    http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { test } from "@jupyterlab/galata";
import { expect } from "@playwright/test";
import * as path from "path";

test.setTimeout(460000);

test.describe("Visual Regression", () => {
  test.beforeEach(async ({ page, tmpPath }) => {
    await page.contents.uploadDirectory(
      path.resolve(__dirname, "../../demo-notebooks/guided-demos"),
      tmpPath
    );
    await page.filebrowser.openDirectory(tmpPath);
  });

  test("Run notebook and capture cell outputs", async ({
    page,
    tmpPath,
  }) => {
    const notebook = "3_widget_example.ipynb";
    await page.notebook.openByPath(`${tmpPath}/${notebook}`);
    await page.notebook.activate(notebook);

    const captures: (Buffer | null)[] = []; // Array to store cell screenshots
    const cellCount = await page.notebook.getCellCount();

    // Run all cells and capture their screenshots
    await page.notebook.runCellByCell({
      onAfterCellRun: async (cellIndex: number) => {
        const cell = await page.notebook.getCellOutput(cellIndex);
        if (cell && (await cell.isVisible())) {
          captures[cellIndex] = await cell.screenshot(); // Save the screenshot by cell index
        }
        await page.addStyleTag({ content: '.jp-cell-toolbar { display: none !important; }' });
      },
    });

    await page.notebook.save();

    // Ensure that each cell's screenshot is captured
    for (let i = 0; i < cellCount; i++) {
      const image = `widgets-cell-${i}.png`;

      if (captures[i]) {
        expect.soft(captures[i]).toMatchSnapshot(image); // Compare pre-existing capture
        continue;
      }
    }
  });
});
