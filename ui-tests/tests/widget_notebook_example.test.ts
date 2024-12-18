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
    const namespace = 'default';
    await page.notebook.openByPath(`${tmpPath}/${notebook}`);
    await page.notebook.activate(notebook);

    // Hide the cell toolbar before capturing the screenshots
    await page.addStyleTag({ content: '.jp-cell-toolbar { display: none !important; }' });
    // Hide the file explorer
    await page.keyboard.press('Control+Shift+F');

    const captures: (Buffer | null)[] = []; // Array to store cell screenshots
    const cellCount = await page.notebook.getCellCount();
    console.log(`Cell count: ${cellCount}`);

    // Run all cells and capture their screenshots
    await page.notebook.runCellByCell({
      onAfterCellRun: async (cellIndex: number) => {
        const cell = await page.notebook.getCellOutput(cellIndex);
        if (cell && (await cell.isVisible())) {
          captures[cellIndex] = await cell.screenshot(); // Save the screenshot by cell index
        }
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

    // At this point, all cells have been ran, and their screenshots have been captured.
    // We now interact with the widgets in the notebook.
    const upDownWidgetCellIndex = 3; // 4 on OpenShift

    await waitForWidget(page, upDownWidgetCellIndex, 'input[type="checkbox"]');
    await waitForWidget(page, upDownWidgetCellIndex, 'button:has-text("Cluster Down")');
    await waitForWidget(page, upDownWidgetCellIndex, 'button:has-text("Cluster Up")');

    await interactWithWidget(page, upDownWidgetCellIndex, 'input[type="checkbox"]', async (checkbox) => {
      await checkbox.click();
      const isChecked = await checkbox.isChecked();
      expect(isChecked).toBe(true);
    });

    await interactWithWidget(page, upDownWidgetCellIndex, 'button:has-text("Cluster Down")', async (button) => {
      await button.click();
      const clusterDownMessage = await page.waitForSelector('text=The requested resource could not be located.', { timeout: 5000 });
      expect(await clusterDownMessage.innerText()).toContain('The requested resource could not be located.');
    });

    await interactWithWidget(page, upDownWidgetCellIndex, 'button:has-text("Cluster Up")', async (button) => {
      await button.click();

      const successMessage = await page.waitForSelector('text=Ray Cluster: \'widgettest\' has successfully been created', { timeout: 10000 });
      expect(successMessage).not.toBeNull();

      const resourcesMessage = await page.waitForSelector('text=Waiting for requested resources to be set up...');
      expect(resourcesMessage).not.toBeNull();

      const upAndRunningMessage = await page.waitForSelector('text=Requested cluster is up and running!');
      expect(upAndRunningMessage).not.toBeNull();

      const dashboardReadyMessage = await page.waitForSelector('text=Dashboard is ready!');
      expect(dashboardReadyMessage).not.toBeNull();
    });

    await runPreviousCell(page, cellCount, '(<CodeFlareClusterStatus.READY: 1>, True)');

    await interactWithWidget(page, upDownWidgetCellIndex, 'button:has-text("Cluster Down")', async (button) => {
      await button.click();
      const clusterDownMessage = await page.waitForSelector('text=Ray Cluster: \'widgettest\' has successfully been deleted', { timeout: 5000 });
      expect(clusterDownMessage).not.toBeNull();
    });

    await runPreviousCell(page, cellCount, '(<CodeFlareClusterStatus.UNKNOWN: 6>, False)');

    // Replace text in ClusterConfiguration to run a new RayCluster
    const cell = page.getByText('widgettest').first();
    await cell.fill('"widgettest-1"');
    await page.notebook.runCell(cellCount - 3, true); // Run ClusterConfiguration cell

    await interactWithWidget(page, upDownWidgetCellIndex, 'button:has-text("Cluster Up")', async (button) => {
      await button.click();
      const successMessage = await page.waitForSelector('text=Ray Cluster: \'widgettest-1\' has successfully been created', { timeout: 10000 });
      expect(successMessage).not.toBeNull();
    });

    const viewClustersCellIndex = 4; // 5 on OpenShift
    await page.notebook.runCell(cellCount - 2, true);

    // Wait until the RayCluster status in the table updates to "Ready"
    await interactWithWidget(page, viewClustersCellIndex, 'button:has-text("Refresh Data")', async (button) => {
      let clusterReady = false;
      const maxRefreshRetries = 24; // 24 retries * 5 seconds = 120 seconds
      let numRefreshRetries = 0;
      while (!clusterReady && numRefreshRetries < maxRefreshRetries) {
        await button.click();
        try {
          await page.waitForSelector('text=Ready ✓', { timeout: 5000 });
          clusterReady = true;
        }
        catch (e) {
          console.log(`Cluster not ready yet. Retrying...`);
          numRefreshRetries++;
        }
      }
      expect(clusterReady).toBe(true);
    });

    await interactWithWidget(page, viewClustersCellIndex, 'button:has-text("Open Ray Dashboard")', async (button) => {
      await button.click();
      const successMessage = await page.waitForSelector('text=Opening Ray Dashboard for widgettest-1 cluster', { timeout: 5000 });
      expect(successMessage).not.toBeNull();
    });

    await interactWithWidget(page, viewClustersCellIndex, 'button:has-text("View Jobs")', async (button) => {
      await button.click();
      const successMessage = await page.waitForSelector('text=Opening Ray Jobs Dashboard for widgettest-1 cluster', { timeout: 5000 });
      expect(successMessage).not.toBeNull();
    });

    await interactWithWidget(page, viewClustersCellIndex, 'button:has-text("Delete Cluster")', async (button) => {
      await button.click();

      const noClustersMessage = await page.waitForSelector(`text=No clusters found in the ${namespace} namespace.`, { timeout: 5000 });
      expect(noClustersMessage).not.toBeNull();
      const successMessage = await page.waitForSelector(`text=Cluster widgettest-1 in the ${namespace} namespace was deleted successfully.`, { timeout: 5000 });
      expect(successMessage).not.toBeNull();
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
