import { expect, test } from '@jupyterlab/galata';

test.describe('Notebook Tests', () => {
  test('Create New Notebook', async ({ page, tmpPath }) => {
    const fileName = 'create_test.ipynb';
    await page.notebook.createNew(fileName);
    expect(
      await page.waitForSelector(`[role="main"] >> text=${fileName}`)
    ).toBeTruthy();

    expect(await page.contents.fileExists(`${tmpPath}/${fileName}`)).toEqual(
      true
    );
  });
});
