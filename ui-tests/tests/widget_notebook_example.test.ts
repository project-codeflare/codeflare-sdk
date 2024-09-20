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

test.describe("Visual Regression", () => {
  test.beforeEach(async ({ page, tmpPath }) => {
    await page.contents.uploadDirectory(
      path.resolve(__dirname, "../../demo-notebooks/guided-demos"),
      tmpPath
    );
    await page.filebrowser.openDirectory(tmpPath);
  });

  test("Run notebook, capture cell outputs, and test widgets", async ({
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

    const widgetCellIndex = 3;

    await waitForWidget(page, widgetCellIndex, 'input[type="checkbox"]');
    await waitForWidget(page, widgetCellIndex, 'button:has-text("Cluster Down")');
    await waitForWidget(page, widgetCellIndex, 'button:has-text("Cluster Up")');

    await interactWithWidget(page, widgetCellIndex, 'input[type="checkbox"]', async (checkbox) => {
      await checkbox.click();
      const isChecked = await checkbox.isChecked();
      expect(isChecked).toBe(true);
    });

    await interactWithWidget(page, widgetCellIndex, 'button:has-text("Cluster Down")', async (button) => {
      await button.click();
      const clusterDownMessage = await page.waitForSelector('text=No instances found, nothing to be done.', { timeout: 5000 });
      expect(clusterDownMessage).not.toBeNull();
    });

    await interactWithWidget(page, widgetCellIndex, 'button:has-text("Cluster Up")', async (button) => {
      await button.click();

      const successMessage = await page.waitForSelector('text=Ray Cluster: \'raytest\' has successfully been created', { timeout: 10000 });
      expect(successMessage).not.toBeNull();

      const resourcesMessage = await page.waitForSelector('text=Waiting for requested resources to be set up...');
      expect(resourcesMessage).not.toBeNull();

      const upAndRunningMessage = await page.waitForSelector('text=Requested cluster is up and running!');
      expect(upAndRunningMessage).not.toBeNull();

      const dashboardReadyMessage = await page.waitForSelector('text=Dashboard is ready!');
      expect(dashboardReadyMessage).not.toBeNull();
    });

    await runPreviousCell(page, cellCount, '(<CodeFlareClusterStatus.READY: 1>, True)');

    await interactWithWidget(page, widgetCellIndex, 'button:has-text("Cluster Down")', async (button) => {
      await button.click();
      const clusterDownMessage = await page.waitForSelector('text=Ray Cluster: \'raytest\' has successfully been deleted', { timeout: 5000 });
      expect(clusterDownMessage).not.toBeNull();
    });

    await runPreviousCell(page, cellCount, '(<CodeFlareClusterStatus.UNKNOWN: 6>, False)');
  });
});

async function waitForWidget(page, cellIndex: number, widgetSelector: string, timeout = 5000) {
  const widgetCell = await page.notebook.getCellOutput(cellIndex);

  if (widgetCell) {
    await widgetCell.waitForSelector(widgetSelector, { timeout });
  }
}

async function interactWithWidget(page, cellIndex: number, widgetSelector: string, action: (widget) => Promise<void>) {
  const widgetCell = await page.notebook.getCellOutput(cellIndex);

  if (widgetCell) {
    const widget = await widgetCell.$(widgetSelector);
    if (widget) {
      await action(widget);
    }
  }
}

async function runPreviousCell(page, cellCount, expectedMessage) {
  const runSuccess = await page.notebook.runCell(cellCount - 1); expect(runSuccess).toBe(true);
  const lastCellOutput = await page.notebook.getCellOutput(cellCount - 1);
  const newOutput = await lastCellOutput.evaluate((output) => output.textContent);

  if (expectedMessage) {
    expect(newOutput).toContain(expectedMessage);
  }

  return lastCellOutput;
}
