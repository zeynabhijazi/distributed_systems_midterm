
import { useEffect, useState } from 'react'
import './App.css'

const API_KEY = 'exam-demo-key'

const authHeaders = {
  'X-API-Key': API_KEY,
}

function App() {
  // Cluster monitoring
  const [cluster, setCluster] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Bucket management
  const [buckets, setBuckets] = useState([])
  const [bucketName, setBucketName] = useState('')
  const [bucketMessage, setBucketMessage] = useState('')
  const [bucketLoading, setBucketLoading] = useState(false)

  // File upload
  const [selectedBucket, setSelectedBucket] = useState('')
  const [selectedFile, setSelectedFile] = useState(null)
  const [uploadMessage, setUploadMessage] = useState('')
  const [uploadLoading, setUploadLoading] = useState(false)
  const [fileInputKey, setFileInputKey] = useState(0)

  // Object listing and download
  const [objects, setObjects] = useState([])
  const [objectsLoading, setObjectsLoading] = useState(false)
  const [objectMessage, setObjectMessage] = useState('')
  const [downloadingKey, setDownloadingKey] = useState(null)

  // Search
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searchMessage, setSearchMessage] = useState('')
  const [searchLoading, setSearchLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)

  // Delete
  const [deletingKey, setDeletingKey] = useState(null)

  function objectUrl(bucket, key) {
    const encodedKey = key
      .split('/')
      .map(encodeURIComponent)
      .join('/')

    return (
      `/api/objects/${encodeURIComponent(bucket)}/${encodedKey}`
    )
  }

  async function getErrorMessage(response) {
    const data = await response.json().catch(() => ({}))

    if (typeof data.detail === 'string') {
      return data.detail
    }

    return `HTTP ${response.status}`
  }

  // -----------------------------
  // CLUSTER MONITORING
  // -----------------------------

  async function loadCluster() {
    setLoading(true)
    setError('')

    try {
      const response = await fetch('/api/cluster/status', {
        headers: authHeaders,
      })

      if (!response.ok) {
        throw new Error(await getErrorMessage(response))
      }

      setCluster(await response.json())
    } catch (err) {
      setError(`Could not load cluster status: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  // -----------------------------
  // BUCKET MANAGEMENT
  // -----------------------------

  async function loadBuckets() {
    try {
      const response = await fetch('/api/buckets', {
        headers: authHeaders,
      })

      if (!response.ok) {
        throw new Error(await getErrorMessage(response))
      }

      const data = await response.json()
      setBuckets(data)

      setSelectedBucket((current) => {
        if (data.some((bucket) => bucket.name === current)) {
          return current
        }

        return data.length > 0 ? data[0].name : ''
      })
    } catch (err) {
      setBucketMessage(`Failed to load buckets: ${err.message}`)
    }
  }

  async function createBucket(event) {
    event.preventDefault()

    const name = bucketName.trim().toLowerCase()

    if (!name) {
      setBucketMessage('Please enter a bucket name')
      return
    }

    setBucketLoading(true)
    setBucketMessage('')

    try {
      const response = await fetch(
        `/api/buckets/${encodeURIComponent(name)}`,
        {
          method: 'POST',
          headers: authHeaders,
        }
      )

      if (!response.ok) {
        throw new Error(await getErrorMessage(response))
      }

      setBucketMessage(`Bucket "${name}" created successfully`)
      setBucketName('')

      await loadBuckets()
      setSelectedBucket(name)
    } catch (err) {
      setBucketMessage(`Error: ${err.message}`)
    } finally {
      setBucketLoading(false)
    }
  }

  // -----------------------------
  // FILE UPLOAD
  // -----------------------------

  async function uploadFile(event) {
    event.preventDefault()

    if (!selectedBucket || !selectedFile) {
      setUploadMessage('Error: Select a bucket and a file')
      return
    }

    setUploadLoading(true)
    setUploadMessage('')

    const fileName = selectedFile.name

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const response = await fetch(
        objectUrl(selectedBucket, fileName),
        {
          method: 'POST',
          headers: authHeaders,
          body: formData,
        }
      )

      if (!response.ok) {
        throw new Error(await getErrorMessage(response))
      }

      const data = await response.json()

      setUploadMessage(
        `File "${fileName}" uploaded successfully. ` +
        `Version: ${data.version}, ` +
        `Chunks: ${data.chunks}, ` +
        `Size: ${data.size} bytes.`
      )

      setSelectedFile(null)
      setFileInputKey((key) => key + 1)

      await loadObjects(selectedBucket)
      await loadCluster()
    } catch (err) {
      setUploadMessage(`Error: ${err.message}`)
    } finally {
      setUploadLoading(false)
    }
  }

  // -----------------------------
  // OBJECT LISTING
  // -----------------------------

  async function loadObjects(bucket) {
    if (!bucket) {
      setObjects([])
      return
    }

    setObjectsLoading(true)
    setObjectMessage('')

    try {
      const response = await fetch(
        `/api/objects/?bucket=${encodeURIComponent(bucket)}`,
        {
          headers: authHeaders,
        }
      )

      if (!response.ok) {
        throw new Error(await getErrorMessage(response))
      }

      const data = await response.json()
      setObjects(data)
    } catch (err) {
      setObjects([])
      setObjectMessage(`Error loading objects: ${err.message}`)
    } finally {
      setObjectsLoading(false)
    }
  }

  // -----------------------------
  // FILE DOWNLOAD
  // -----------------------------

  async function downloadObject(object) {
    setDownloadingKey(object.key)
    setObjectMessage('')

    try {
      const response = await fetch(
        objectUrl(object.bucket, object.key),
        {
          headers: authHeaders,
        }
      )

      if (!response.ok) {
        throw new Error(await getErrorMessage(response))
      }

      const blob = await response.blob()
      const url = URL.createObjectURL(blob)

      const link = document.createElement('a')
      link.href = url
      link.download = object.key.split('/').pop() || 'download'

      document.body.appendChild(link)
      link.click()
      link.remove()

      setTimeout(() => URL.revokeObjectURL(url), 1000)

      setObjectMessage(
        `File "${object.key}" downloaded successfully.`
      )
    } catch (err) {
      setObjectMessage(`Download failed: ${err.message}`)
    } finally {
      setDownloadingKey(null)
    }
  }

  // -----------------------------
  // OBJECT SEARCH
  // -----------------------------

  async function searchObjects(event) {
    event.preventDefault()

    const query = searchQuery.trim()

    if (!query) {
      setSearchMessage('Please enter a search keyword')
      setSearchResults([])
      setHasSearched(false)
      return
    }

    setSearchLoading(true)
    setSearchMessage('')
    setHasSearched(true)

    try {
      const response = await fetch(
        `/api/search?q=${encodeURIComponent(query)}`,
        {
          headers: authHeaders,
        }
      )

      if (!response.ok) {
        throw new Error(await getErrorMessage(response))
      }

      const data = await response.json()
      setSearchResults(data)

      setSearchMessage(
        `Found ${data.length} matching object(s).`
      )
    } catch (err) {
      setSearchResults([])
      setSearchMessage(`Search failed: ${err.message}`)
    } finally {
      setSearchLoading(false)
    }
  }

  function clearSearch() {
    setSearchQuery('')
    setSearchResults([])
    setSearchMessage('')
    setHasSearched(false)
  }

  // -----------------------------
  // FILE DELETION
  // -----------------------------

  async function deleteObject(object) {
    const confirmed = window.confirm(
      `Delete "${object.key}" from bucket "${object.bucket}"?\n\n` +
      'All versions of this object will be deleted.'
    )

    if (!confirmed) {
      return
    }

    const identifier = `${object.bucket}/${object.key}`

    setDeletingKey(identifier)
    setObjectMessage('')

    try {
      const response = await fetch(
        objectUrl(object.bucket, object.key),
        {
          method: 'DELETE',
          headers: authHeaders,
        }
      )

      if (!response.ok) {
        throw new Error(await getErrorMessage(response))
      }

      const data = await response.json()

      setObjectMessage(
        `File "${object.key}" deleted successfully. ` +
        `Unused chunks: ${data.unused_chunks ?? 0}.`
      )

      // Refresh the list after deletion
      await loadObjects(object.bucket)
      await loadCluster()

      // Remove deleted file from previous search results
      setSearchResults((current) =>
        current.filter(
          (item) =>
            item.bucket !== object.bucket ||
            item.key !== object.key
        )
      )
    } catch (err) {
      setObjectMessage(`Deletion failed: ${err.message}`)
    } finally {
      setDeletingKey(null)
    }
  }

  // -----------------------------
  // INITIAL LOAD
  // -----------------------------

  useEffect(() => {
    loadCluster()
    loadBuckets()
  }, [])

  useEffect(() => {
    loadObjects(selectedBucket)
  }, [selectedBucket])

  return (
    <div className="container">
      <h1>Distributed Storage System</h1>
      <p>Storage Management Dashboard</p>

      {/* CLUSTER MONITORING */}
      <section>
        <h2>Cluster Monitoring</h2>

        <button onClick={loadCluster} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh Status'}
        </button>

        {error && <p className="error">{error}</p>}

        {cluster && (
          <>
            <div className="summary">
              <p>Total Nodes: {cluster.total_nodes}</p>
              <p>Healthy Nodes: {cluster.healthy_nodes}</p>
              <p>Offline Nodes: {cluster.offline_nodes}</p>
            </div>

            <h3>Storage Nodes</h3>

            <table>
              <thead>
                <tr>
                  <th>Node ID</th>
                  <th>Status</th>
                  <th>Free Space</th>
                  <th>Chunks</th>
                </tr>
              </thead>

              <tbody>
                {cluster.nodes.map((node, index) => (
                  <tr key={node.node_id ?? index}>
                    <td>{node.node_id}</td>
                    <td>{node.status}</td>
                    <td>{node.free_space ?? 'N/A'}</td>
                    <td>{node.chunk_count ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      {/* BUCKET MANAGEMENT */}
      <section className="bucket-section">
        <h2>Bucket Management</h2>

        <form onSubmit={createBucket}>
          <input
            type="text"
            placeholder="Enter bucket name"
            value={bucketName}
            onChange={(e) => setBucketName(e.target.value)}
            required
          />

          <button type="submit" disabled={bucketLoading}>
            {bucketLoading ? 'Creating...' : 'Create Bucket'}
          </button>
        </form>

        {bucketMessage && (
          <p className={
            bucketMessage.startsWith('Error') ||
            bucketMessage.startsWith('Failed')
              ? 'error'
              : 'success'
          }>
            {bucketMessage}
          </p>
        )}

        <button type="button" onClick={loadBuckets}>
          Refresh Buckets
        </button>

        <h3>Existing Buckets</h3>

        {buckets.length === 0 ? (
          <p>No buckets found.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Bucket Name</th>
                <th>Created At</th>
              </tr>
            </thead>

            <tbody>
              {buckets.map((bucket) => (
                <tr key={bucket.name}>
                  <td>{bucket.name}</td>
                  <td>
                    {bucket.created_at
                      ? new Date(bucket.created_at).toLocaleString()
                      : 'N/A'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* FILE UPLOAD */}
      <section className="upload-section">
        <h2>Upload File</h2>

        <form onSubmit={uploadFile}>
          <label htmlFor="upload-bucket">
            Select Bucket
          </label>

          <select
            id="upload-bucket"
            value={selectedBucket}
            onChange={(e) => setSelectedBucket(e.target.value)}
            required
          >
            {buckets.length === 0 && (
              <option value="">No buckets available</option>
            )}

            {buckets.map((bucket) => (
              <option key={bucket.name} value={bucket.name}>
                {bucket.name}
              </option>
            ))}
          </select>

          <label htmlFor="upload-file">
            Choose File
          </label>

          <input
            key={fileInputKey}
            id="upload-file"
            type="file"
            onChange={(e) => {
              setSelectedFile(e.target.files?.[0] || null)
              setUploadMessage('')
            }}
            required
          />

          <button
            type="submit"
            disabled={
              uploadLoading ||
              !selectedBucket ||
              !selectedFile
            }
          >
            {uploadLoading ? 'Uploading...' : 'Upload File'}
          </button>
        </form>

        {uploadMessage && (
          <p className={
            uploadMessage.startsWith('Error')
              ? 'error'
              : 'success'
          }>
            {uploadMessage}
          </p>
        )}
      </section>

      {/* STORED OBJECTS */}
      <section className="objects-section">
        <h2>Stored Objects</h2>

        <p>
          Selected Bucket: <strong>{selectedBucket || 'None'}</strong>
        </p>

        <button
          onClick={() => loadObjects(selectedBucket)}
          disabled={objectsLoading || !selectedBucket}
        >
          {objectsLoading ? 'Loading...' : 'Refresh Objects'}
        </button>

        {objectMessage && (
          <p className={
            objectMessage.startsWith('Deletion failed') ||
            objectMessage.startsWith('Download failed') ||
            objectMessage.startsWith('Error')
              ? 'error'
              : 'success'
          }>
            {objectMessage}
          </p>
        )}

        {objects.length === 0 ? (
          <p>No objects found in this bucket.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>File Name</th>
                <th>Size (Bytes)</th>
                <th>Version</th>
                <th>Uploaded At</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {objects.map((object, index) => {
                const identifier = `${object.bucket}/${object.key}`

                return (
                  <tr
                    key={`${identifier}-${object.version}-${index}`}
                  >
                    <td>{object.key}</td>
                    <td>{object.size}</td>
                    <td>{object.version}</td>
                    <td>
                      {object.created_at
                        ? new Date(object.created_at).toLocaleString()
                        : 'N/A'}
                    </td>
                    <td className="actions">
                      <button
                        onClick={() => downloadObject(object)}
                        disabled={
                          downloadingKey !== null ||
                          deletingKey !== null
                        }
                      >
                        {downloadingKey === object.key
                          ? 'Downloading...'
                          : 'Download'}
                      </button>

                      <button
                        className="delete-button"
                        onClick={() => deleteObject(object)}
                        disabled={deletingKey !== null}
                      >
                        {deletingKey === identifier
                          ? 'Deleting...'
                          : 'Delete'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        <p className="note">
          Download retrieves the latest version. Delete removes
          all versions of the selected file.
        </p>
      </section>

      {/* OBJECT SEARCH */}
      <section className="search-section">
        <h2>Search Objects</h2>

        <form onSubmit={searchObjects}>
          <input
            type="text"
            placeholder="Search by file or bucket name"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            required
          />

          <button type="submit" disabled={searchLoading}>
            {searchLoading ? 'Searching...' : 'Search'}
          </button>

          <button type="button" onClick={clearSearch}>
            Clear
          </button>
        </form>

        {searchMessage && (
          <p className={
            searchMessage.startsWith('Search failed')
              ? 'error'
              : 'success'
          }>
            {searchMessage}
          </p>
        )}

        {hasSearched && (
          searchResults.length === 0 ? (
            <p>No matching objects found.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Bucket</th>
                  <th>File Name</th>
                  <th>Size (Bytes)</th>
                  <th>Version</th>
                </tr>
              </thead>

              <tbody>
                {searchResults.map((object, index) => (
                  <tr
                    key={`${object.bucket}-${object.key}-${object.version}-${index}`}
                  >
                    <td>{object.bucket}</td>
                    <td>{object.key}</td>
                    <td>{object.size}</td>
                    <td>{object.version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
      </section>
    </div>
  )
}

export default App
