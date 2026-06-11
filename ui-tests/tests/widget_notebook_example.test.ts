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

test.describe("Widget Functionality", () => {
  test.beforeEach(async ({ page, tmpPath }) => {
    await page.contents.uploadDirectory(
      path.resolve(__dirname, "../../demo-notebooks/guided-demos"),
      tmpPath
    );
    await page.filebrowser.openDirectory(tmpPath);
  });

  test("Run notebook and test widget functionality", async ({
    page,
    tmpPath,
  }) => {
    const notebook = "3_widget_example.ipynb";
    const namespace = 'default';
    await page.notebook.openByPath(`${tmpPath}/${notebook}`);
    await page.notebook.activate(notebook);

    const cellCount = await page.notebook.getCellCount();
    console.log(`Cell count: ${cellCount}`);

    // Run all cells to initialize the notebook
    await page.notebook.runCellByCell();

    await page.notebook.save();

    // Wait for widgets to fully render after cell execution
    await page.waitForTimeout(5000);

    // Test widget functionality through interaction
    const applyDownWidgetCellIndex = 3; // 4 on OpenShift

    // Verify widgets render correctly
    await waitForWidget(page, applyDownWidgetCellIndex, 'input[type="checkbox"]', 30000);

    await waitForWidget(page, applyDownWidgetCellIndex, 'button:has-text("Cluster Down")', 10000);
    await waitForWidget(page, applyDownWidgetCellIndex, 'button:has-text("Cluster Apply")', 10000);

    // Test checkbox interaction
    await interactWithWidget(page, applyDownWidgetCellIndex, 'input[type="checkbox"]', async (checkbox) => {
      await checkbox.click();
      const isChecked = await checkbox.isChecked();
      expect(isChecked).toBe(true);
      // Uncheck it so apply() doesn't call wait_ready() (which has dashboard_check=True issues in KinD)
      await checkbox.click();
      expect(await checkbox.isChecked()).toBe(false);
    });

    // Test Cluster Down button - cluster doesn't exist yet, should show error message
    await interactWithWidget(page, applyDownWidgetCellIndex, 'button:has-text("Cluster Down")', async (button) => {
      await button.click();
      const clusterDownMessage = await page.waitForSelector('text=The requested resource could not be located.', { timeout: 10000 });
      expect(await clusterDownMessage.innerText()).toContain('The requested resource could not be located.');
    });

    // Test Cluster Apply button WITHOUT the wait_ready checkbox checked
    // This avoids the long TLS timeout + dashboard_check issues in KinD
    await interactWithWidget(page, applyDownWidgetCellIndex, 'button:has-text("Cluster Apply")', async (button) => {
      await button.click();

      // The apply() method prints "applied" not "created"
      // Without checkbox, wait_ready() is not called, so we only see the apply message
      const successMessage = await page.waitForSelector('text=Ray Cluster: \'widgettest\' has successfully been applied', { timeout: 30000 });
      expect(successMessage).not.toBeNull();
    });

    // Wait for apply() to complete (widget uses 60s TLS timeout)
    // We wait for either success or failure message from the TLS setup phase
    await page.waitForSelector('text=/Cluster .widgettest. (is ready|resources applied but TLS setup incomplete)/', { timeout: 90000 });

    // Test view_clusters widget
    const viewClustersCellIndex = 4; // 5 on OpenShift
    await page.notebook.runCell(cellCount - 2, true);

    // Wait for view_clusters widget to render
    await waitForWidget(page, viewClustersCellIndex, 'button:has-text("Refresh Data")', 30000);

    // Test Refresh Data button
    await interactWithWidget(page, viewClustersCellIndex, 'button:has-text("Refresh Data")', async (button) => {
      // Just verify the button is clickable
      await button.click();
      // Wait a moment for the refresh to complete
      await page.waitForTimeout(2000);
    });

    // Verify other view_clusters buttons exist
    await waitForWidget(page, viewClustersCellIndex, 'button:has-text("Open Ray Dashboard")', 5000);
    await waitForWidget(page, viewClustersCellIndex, 'button:has-text("View Jobs")', 5000);
    await waitForWidget(page, viewClustersCellIndex, 'button:has-text("Delete Cluster")', 5000);

    // Test Delete Cluster button to clean up
    await interactWithWidget(page, viewClustersCellIndex, 'button:has-text("Delete Cluster")', async (button) => {
      await button.click();
      // Wait for deletion confirmation - increase timeout as cluster deletion can take time
      const successMessage = await page.waitForSelector(`text=Cluster widgettest in the ${namespace} namespace was deleted successfully.`, { timeout: 30000 });
      expect(successMessage).not.toBeNull();
    });
  });
});

async function waitForWidget(page, cellIndex: number, widgetSelector: string, timeout = 5000) {
  const widgetCell = await page.notebook.getCellOutput(cellIndex);

  if (!widgetCell) {
    throw new Error(`Cell ${cellIndex} has no output - widgets not rendered. Check if is_notebook() detection is working.`);
  }
  await widgetCell.waitForSelector(widgetSelector, { timeout });
}

async function interactWithWidget(page, cellIndex: number, widgetSelector: string, action: (widget) => Promise<void>) {
  const widgetCell = await page.notebook.getCellOutput(cellIndex);

  if (!widgetCell) {
    throw new Error(`Cell ${cellIndex} has no output - cannot interact with widget.`);
  }
  const widget = await widgetCell.$(widgetSelector);
  if (!widget) {
    throw new Error(`Widget '${widgetSelector}' not found in cell ${cellIndex}.`);
  }
  await action(widget);
}
