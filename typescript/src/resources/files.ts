/**
 * Files resource -- upload, list, retrieve, download, and delete files.
 *
 * Provides the {@link Files} class for the MiniMax Files API.
 */

import { readFile } from "node:fs/promises";
import { basename } from "node:path";
import { APIResource } from "../resource.js";

// ── Types ───────────────────────────────────────────────────────────────────

export interface FileInfo {
  file_id: string;
  bytes: number;
  created_at: number;
  filename: string;
  purpose: string;
  download_url?: string;
}

// ── Validation ──────────────────────────────────────────────────────────────

const VALID_UPLOAD_PURPOSES = new Set([
  "voice_clone",
  "prompt_audio",
  "t2a_async_input",
]);

function validateUploadPurpose(purpose: string): void {
  if (!VALID_UPLOAD_PURPOSES.has(purpose)) {
    throw new Error(
      `Invalid upload purpose "${purpose}". ` +
        `Must be one of: ${[...VALID_UPLOAD_PURPOSES].sort().join(", ")}`,
    );
  }
}

// ── Files resource ──────────────────────────────────────────────────────────

/**
 * Synchronous files resource for uploading, listing, retrieving,
 * downloading, and deleting files.
 */
export class Files extends APIResource {
  /**
   * Upload a file.
   *
   * @param file - A filesystem path (string) or a Buffer/Blob of file data.
   * @param purpose - The intended use of the file. Must be one of
   *   "voice_clone", "prompt_audio", or "t2a_async_input".
   * @returns A {@link FileInfo} describing the uploaded file.
   */
  async upload(
    file: string | Buffer | Blob,
    purpose: string,
  ): Promise<FileInfo> {
    validateUploadPurpose(purpose);

    let blob: Blob;
    let filename: string;

    if (typeof file === "string") {
      const data = await readFile(file);
      blob = new Blob([data]);
      filename = basename(file);
    } else if (Buffer.isBuffer(file)) {
      blob = new Blob([file]);
      filename = "upload";
    } else {
      blob = file;
      filename = "upload";
    }

    const resp = await this._client.upload(
      "/v1/files/upload",
      blob,
      filename,
      purpose,
    );
    return resp.file as FileInfo;
  }

  /**
   * List files that match the given purpose.
   *
   * @param purpose - Filter files by purpose.
   * @returns A list of {@link FileInfo} objects.
   */
  async list(purpose: string): Promise<FileInfo[]> {
    const resp = await this._client.request("GET", "/v1/files/list", {
      params: { purpose },
    });
    return (resp.files as FileInfo[]) ?? [];
  }

  /**
   * Retrieve metadata (and a temporary download URL) for a file.
   *
   * @param fileId - The identifier of the file to retrieve.
   * @returns A {@link FileInfo} with a download_url (valid for ~1 hr
   *   for video files, ~9 hr for T2A async files).
   */
  async retrieve(fileId: string): Promise<FileInfo> {
    const resp = await this._client.request("GET", "/v1/files/retrieve", {
      params: { file_id: String(Number(fileId)) },
    });
    return resp.file as FileInfo;
  }

  /**
   * Download the raw content of a file.
   *
   * @param fileId - The identifier of the file to download.
   * @returns The file content as an ArrayBuffer.
   */
  async retrieveContent(fileId: string): Promise<ArrayBuffer> {
    return this._client.requestBytes("GET", "/v1/files/retrieve_content", {
      params: { file_id: String(Number(fileId)) },
    });
  }

  /**
   * Delete a file.
   *
   * @param fileId - The identifier of the file to delete.
   * @param purpose - The purpose tag of the file.
   */
  async delete(fileId: string, purpose: string): Promise<void> {
    await this._client.request("POST", "/v1/files/delete", {
      json: { file_id: Number(fileId), purpose },
    });
  }
}
