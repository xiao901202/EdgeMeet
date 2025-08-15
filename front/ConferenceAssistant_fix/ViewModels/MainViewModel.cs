using ConferenceAssistant.Models;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using NAudio.Wave;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Timers;
using ConferenceAssistant.Models;
using System.Windows.Input;



namespace ConferenceAssistant.ViewModels
{
    public class MainViewModel : INotifyPropertyChanged
    {
        private bool _isRecording;
        private bool _isPlaying;
        private string _currentTranscript = string.Empty;
        private string _summary = string.Empty;
        private double _audioLevel;
        private string _recordingStatus = "準備就緒";
        private bool _isProcessing;
        private string _audioFilePath = string.Empty;
        private ConferenceRecord? _selectedRecord;
        private double _playbackPosition;
        private double _totalDuration;
        private string _currentTime = "00:00:00";
        private string _totalTime = "00:00:00";
        private string _recordingTime = "00:00:00";
        private DateTime _recordingStartTime;

        //輸入
        private WaveInEvent? _waveIn;
        private WaveFileWriter? _writer;
        private readonly DispatcherQueue _dispatcherQueue = DispatcherQueue.GetForCurrentThread();

        // 音訊播放
        private AudioFileReader? _audioFileReader;
        private WaveOutEvent? _waveOut;

        private double? _pendingSeekPosition = null;  // 預先記住跳段位置（尚未初始化播放器時）

        public ObservableCollection<string> InputDevices { get; } = new();
        private int _selectedDeviceIndex = 0;






        public int SelectedDeviceIndex
        {
            get => _selectedDeviceIndex;
            set => SetProperty(ref _selectedDeviceIndex, value);
        }

        public ObservableCollection<string> OutputDevices { get; } = new();

        private int _selectedOutputDeviceIndex = 0;
        public int SelectedOutputDeviceIndex
        {
            get => _selectedOutputDeviceIndex;
            set => SetProperty(ref _selectedOutputDeviceIndex, value);
        }

        private static readonly HttpClient _httpClient = new HttpClient()
        {
            Timeout = TimeSpan.FromMinutes(5) // 設定較長的超時時間
        };
        private const string ApiBaseUrl = "http://localhost:8000";
        private const string TranscribeEndpoint = "/transcribe";
        private const string RecordEndpoint = "/record";
        private const string GetRecordsEndpoint = "/records";
        // 儲存錄音檔案的目錄
        private readonly string _recordingsDirectory;
        private readonly DispatcherTimer _playbackTimer = new() { Interval = TimeSpan.FromSeconds(1) };

        public ObservableCollection<IndexedSample> WaveformSamples { get; } = new();

        public double WaveformCanvasWidth => WaveformSamples.Count * 3;
        public async Task LoadWaveformAsync(string filePath)
        {
            if (!File.Exists(filePath)) return;

            await Task.Run(() =>
            {
                try
                {
                    var tempSamples = new List<IndexedSample>();
                    using var reader = new AudioFileReader(filePath);
                    var buffer = new float[reader.WaveFormat.SampleRate]; // 1 秒 44100 samples
                    int index = 0;

                    while (true)
                    {
                        int samplesRead = reader.Read(buffer, 0, buffer.Length);
                        if (samplesRead == 0) break;

                        // 取樣間隔，壓縮資料量（例如每 500 個 samples 取一個峰值）
                        int stride = 500;
                        for (int i = 0; i < samplesRead; i += stride)
                        {
                            float max = 0;
                            for (int j = i; j < i + stride && j < samplesRead; j++)
                            {
                                max = Math.Max(max, Math.Abs(buffer[j]));
                            }
                            tempSamples.Add(new IndexedSample { Index = index++, Value = max });
                        }
                    }

                    // 回到 UI 執行緒更新
                    _dispatcherQueue.TryEnqueue(() =>
                    {
                        WaveformSamples.Clear();
                        foreach (var sample in tempSamples)
                            WaveformSamples.Add(sample);
                        OnPropertyChanged(nameof(WaveformCanvasWidth));
                    });
                }
                catch (Exception ex)
                {
                    Debug.WriteLine($"讀取波形失敗: {ex.Message}");
                }
            });
        }

        public MainViewModel()
        {


            ConferenceRecords = new ObservableCollection<ConferenceRecord>();
            CurrentTranscriptSegments = new ObservableCollection<TranscriptSegment>();

            // 建立錄音檔案目錄
            _recordingsDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "ConferenceAssistant", "Recordings");
            Directory.CreateDirectory(_recordingsDirectory);


            //  掃描音訊輸入裝置（麥克風）
            for (int i = 0; i < WaveIn.DeviceCount; i++)
            {
                var deviceInfo = WaveIn.GetCapabilities(i);
                InputDevices.Add(deviceInfo.ProductName);
            }
            // 音訊輸出設備（喇叭、耳機）
            for (int i = 0; i < WaveOut.DeviceCount; i++)
            {
                var deviceInfo = WaveOut.GetCapabilities(i);
                OutputDevices.Add(deviceInfo.ProductName);
            }


            _playbackTimer = new DispatcherTimer
            {
                Interval = TimeSpan.FromSeconds(1)
            };

            _playbackTimer.Tick += (s, e) =>
            {
                if (_audioFileReader != null && _waveOut?.PlaybackState == PlaybackState.Playing)
                {
                    PlaybackPosition = _audioFileReader.CurrentTime.TotalSeconds;
                    UpdateTimeDisplay();
                }
            };

            _playbackTimer.Start();


        }



        // 上傳音檔到 FastAPI 並取得轉錄結果
        public async Task<TranscriptionResult?> UploadAndTranscribeAsync(string filePath)
        {
            if (!File.Exists(filePath))
            {
                Debug.WriteLine($"檔案不存在: {filePath}");
                return null;
            }

            try
            {
                using var form = new MultipartFormDataContent();
                using var fileStream = File.OpenRead(filePath);
                using var fileContent = new StreamContent(fileStream);

                // 設定正確的 Content-Type
                var extension = Path.GetExtension(filePath).ToLower();
                var contentType = extension switch
                {
                    ".mp3" => "audio/mpeg",
                    ".wav" => "audio/wav",
                    ".m4a" => "audio/mp4",
                    ".flac" => "audio/flac",
                    _ => "audio/mpeg"
                };

                fileContent.Headers.ContentType = new MediaTypeHeaderValue(contentType);
                form.Add(fileContent, "file", Path.GetFileName(filePath));

                Debug.WriteLine($"開始上傳檔案: {Path.GetFileName(filePath)}");

                var response = await _httpClient.PostAsync($"{ApiBaseUrl}{TranscribeEndpoint}", form);

                if (response.IsSuccessStatusCode)
                {
                    var jsonResponse = await response.Content.ReadAsStringAsync();
                    Debug.WriteLine($"收到回應: {jsonResponse}");

                    // 解析 JSON 回應
                    var options = new JsonSerializerOptions
                    {
                        PropertyNameCaseInsensitive = true
                    };

                    var apiResponse = JsonSerializer.Deserialize<TranscriptionApiResponse>(jsonResponse, options);

                    if (apiResponse == null)
                    {
                        Debug.WriteLine("API 回傳解析失敗");
                        return null;
                    }

                    return new TranscriptionResult
                    {
                        Summary = apiResponse.Summary,
                        SummaryUrl = apiResponse.Paths.Summary_Url,
                        TranscriptUrl = apiResponse.Paths.Transcript_Url,
                        Segments = new List<TranscriptSegment>
    {
                            new TranscriptSegment
                            {
                                TimeStamp = TimeSpan.Zero,
                                Speaker = "AI",
                                Text = apiResponse.Transcript
                            }
    }
                    };

                }
                else
                {
                    var error = await response.Content.ReadAsStringAsync();
                    Debug.WriteLine($"上傳失敗: {response.StatusCode} - {error}");
                    RecordingStatus = $"轉錄失敗: {response.StatusCode}";
                }
            }
            catch (TaskCanceledException)
            {
                Debug.WriteLine("請求超時");
                RecordingStatus = "轉錄超時，請稍後再試";
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"上傳時發生錯誤: {ex.Message}");
                RecordingStatus = $"錯誤: {ex.Message}";
            }

            return null;
        }

        // 將完整的會議記錄上傳到後端
        public async Task UploadConferenceRecordAsync(ConferenceRecord record)
        {
            try
            {
                var recordData = new
                {
                    id = record.Id.ToString(),
                    title = record.Title,
                    date = record.Date.ToString("O"), // ISO 8601 格式
                    duration = record.Duration.TotalSeconds,
                    file_path = record.FilePath,
                    summary = record.Summary,
                    is_transcribed = record.IsTranscribed,
                    transcript_segments = record.TranscriptSegments.Select(s => new
                    {
                        timestamp = (int)s.TimeStamp.TotalSeconds,
                        text = s.Text,
                        speaker = s.Speaker
                    }).ToList()
                };

                var json = JsonSerializer.Serialize(recordData);
                var content = new StringContent(json, Encoding.UTF8, "application/json");

                var response = await _httpClient.PostAsync($"{ApiBaseUrl}{RecordEndpoint}", content);

                if (response.IsSuccessStatusCode)
                {
                    Debug.WriteLine("會議記錄上傳成功");
                }
                else
                {
                    var error = await response.Content.ReadAsStringAsync();
                    Debug.WriteLine($"會議記錄上傳失敗: {error}");
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"上傳會議記錄時發生錯誤: {ex.Message}");
            }
        }
        //private const string GetRecordsEndpoint = "/records"; // 新增這行
        // 取得會議記錄列表
        public async Task LoadConferenceRecordsAsync()
        {
            try
            {
                var response = await _httpClient.GetAsync($"{ApiBaseUrl}{GetRecordsEndpoint}");
                if (response.IsSuccessStatusCode)
                {
                    var json = await response.Content.ReadAsStringAsync();
                    var options = new JsonSerializerOptions
                    {
                        PropertyNameCaseInsensitive = true
                    };

                    var records = JsonSerializer.Deserialize<List<ConferenceRecordDto>>(json, options);
                    if (records != null)
                    {
                        ConferenceRecords.Clear();

                        foreach (var dto in records)
                        {
                            var record = new ConferenceRecord
                            {
                                Id = Guid.TryParse(dto.Id, out var guid) ? guid : Guid.NewGuid(),
                                Title = dto.Title,
                                Date = DateTime.Parse(dto.Date),
                                Duration = TimeSpan.FromSeconds(dto.Duration),
                                FilePath = dto.FilePath,
                                Summary = dto.Summary,
                                IsTranscribed = dto.IsTranscribed
                            };

                            foreach (var s in dto.TranscriptSegments)
                            {
                                record.TranscriptSegments.Add(new TranscriptSegment
                                {
                                    TimeStamp = TimeSpan.FromSeconds(s.Timestamp),
                                    Text = s.Text,
                                    Speaker = s.Speaker
                                });
                            }

                            ConferenceRecords.Add(record);
                        }
                    }
                }
                else
                {
                    Debug.WriteLine($"取得記錄失敗: {response.StatusCode}");
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"載入記錄發生錯誤: {ex.Message}");
            }
        }

        //套用播放結束事件的處理方法
        private void OnPlaybackStopped(object? sender, StoppedEventArgs e)
        {
            _dispatcherQueue.TryEnqueue(() =>
            {
                IsPlaying = false;
                PlaybackPosition = 0;
                CurrentTime = "00:00:00";

                _waveOut?.Dispose();
                _audioFileReader?.Dispose();
                _waveOut = null;
                _audioFileReader = null;
            });
        }
        private void ResetPlaybackState()
        {
            PlaybackPosition = 0;
            CurrentTime = "00:00:00";
            IsPlaying = false;

            _waveOut?.Dispose();
            _audioFileReader?.Dispose();
            _waveOut = null;
            _audioFileReader = null;
        }

        // 停止錄音並自動處理
        public async Task StopRecordingAsync()
        {
            IsRecording = false;
            RecordingStatus = "儲存錄音...";
            IsProcessing = true;

            var recordingDuration = DateTime.Now - _recordingStartTime;
            // 停止錄音
            _waveIn?.StopRecording();
            _waveIn?.Dispose();
            _waveIn = null;

            _writer?.Dispose();
            _writer = null;

            // 創建新的會議記錄
            var newRecord = new ConferenceRecord
            {
                Id = Guid.NewGuid(),
                Title = $"會議記錄 {DateTime.Now:MM/dd HH:mm}",
                Date = DateTime.Now,
                Duration = recordingDuration,
                FilePath = AudioFilePath,
                IsTranscribed = false
            };

            ConferenceRecords.Insert(0, newRecord);
            SelectedRecord = newRecord;

            IsProcessing = false;
            RecordingStatus = "錄音完成";
            RecordingTime = "00:00:00";
        }

        // 開始轉錄（可以從 UI 手動觸發或自動觸發）
        public async Task StartTranscriptionAsync()
        {
            if (SelectedRecord == null || string.IsNullOrEmpty(SelectedRecord.FilePath)) return;

            IsProcessing = true;
            RecordingStatus = "正在進行AI語音轉錄...";

            try
            {
                // 上傳音檔並取得轉錄結果
                var result = await UploadAndTranscribeAsync(SelectedRecord.FilePath);

                if (result != null)
                {
                    //  將後端回傳的 .txt 檔案網址寫入 SelectedRecord
                    SelectedRecord.SummaryUrl = result.SummaryUrl;
                    SelectedRecord.TranscriptUrl = result.TranscriptUrl;

                    // 清空舊的轉錄內容
                    SelectedRecord.TranscriptSegments.Clear();
                    CurrentTranscriptSegments.Clear();

                    // 加入新的轉錄段落
                    foreach (var segment in result.Segments)
                    {
                        var transcriptSegment = new TranscriptSegment
                        {
                            TimeStamp = TimeSpan.FromSeconds(segment.Timestamp),
                            Text = segment.Text,
                            Speaker = segment.Speaker
                        };

                        SelectedRecord.TranscriptSegments.Add(transcriptSegment);
                        CurrentTranscriptSegments.Add(transcriptSegment);
                    }

                    // 設定摘要
                    SelectedRecord.Summary = result.Summary;
                    Summary = result.Summary;

                    // 標記為已轉錄
                    SelectedRecord.IsTranscribed = true;

                    // 上傳完整的會議記錄到後端
                    await UploadConferenceRecordAsync(SelectedRecord);

                    RecordingStatus = "轉錄完成";
                }
                else
                {
                    RecordingStatus = "轉錄失敗";
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"轉錄過程中發生錯誤: {ex.Message}");
                RecordingStatus = $"轉錄錯誤: {ex.Message}";
            }
            finally
            {
                IsProcessing = false;
            }
        }


        // 上傳外部音檔
        public async Task UploadAudioFileAsync(string filePath)
        {
            AudioFilePath = filePath;
            IsProcessing = true;
            RecordingStatus = "處理上傳的音訊...";

            try
            {
                // 複製檔案到應用程式目錄
                var fileName = Path.GetFileName(filePath);
                var targetPath = Path.Combine(_recordingsDirectory, fileName);

                if (filePath != targetPath)
                {
                    File.Copy(filePath, targetPath, true);
                }

                // 建立新記錄
                var newRecord = new ConferenceRecord
                {
                    Id = Guid.NewGuid(),
                    Title = $"上傳: {Path.GetFileNameWithoutExtension(fileName)}",
                    Date = DateTime.Now,
                    Duration = await GetAudioDuration(targetPath), // 需要實作取得音檔長度的方法
                    FilePath = targetPath,
                    IsTranscribed = false
                };

                ConferenceRecords.Insert(0, newRecord);
                SelectedRecord = newRecord;

                // 自動開始轉錄
                await StartTranscriptionAsync();
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"處理上傳檔案時發生錯誤: {ex.Message}");
                RecordingStatus = $"上傳錯誤: {ex.Message}";
            }
            finally
            {
                IsProcessing = false;
            }
        }

        // 取得音檔長度（需要實作）
        private async Task<TimeSpan> GetAudioDuration(string filePath)
        {
            // 這裡應該使用音訊處理庫來取得實際長度
            // 暫時返回預設值
            await Task.CompletedTask;
            return TimeSpan.FromMinutes(10);
        }


        // 屬性和其他方法保持原樣...
        public ObservableCollection<ConferenceRecord> ConferenceRecords { get; }
        public ObservableCollection<TranscriptSegment> CurrentTranscriptSegments { get; }

        public bool IsRecording
        {
            get => _isRecording;
            set => SetProperty(ref _isRecording, value);
        }
        public bool IsPlaying
        {
            get => _isPlaying;
            set => SetProperty(ref _isPlaying, value);
        }


        public double PlaybackPosition
        {
            get => _playbackPosition;
            set
            {
                if (_playbackPosition != value)
                {
                    _playbackPosition = value;
                    OnPropertyChanged();
                    OnPropertyChanged(nameof(CurrentTime));
                }
            }
        }

        public double TotalDuration
        {
            get => _totalDuration;
            set => SetProperty(ref _totalDuration, value);
        }

        public string CurrentTime
        {
            get => _currentTime;
            set => SetProperty(ref _currentTime, value);
        }

        public string TotalTime
        {
            get => _totalTime;
            set => SetProperty(ref _totalTime, value);
        }

        public string RecordingTime
        {
            get => _recordingTime;
            set => SetProperty(ref _recordingTime, value);
        }

        public string RecordingStatus
        {
            get => _recordingStatus;
            set => SetProperty(ref _recordingStatus, value);
        }

        public double AudioLevel
        {
            get => _audioLevel;
            set => SetProperty(ref _audioLevel, value);
        }

        public string CurrentTranscript
        {
            get => _currentTranscript;
            set => SetProperty(ref _currentTranscript, value);
        }

        public string Summary
        {
            get => _summary;
            set => SetProperty(ref _summary, value);
        }

        public bool IsProcessing
        {
            get => _isProcessing;
            set => SetProperty(ref _isProcessing, value);
        }

        public ConferenceRecord? SelectedRecord
        {
            get => _selectedRecord;
            set
            {
                if (SetProperty(ref _selectedRecord, value))
                {
                    StopPlayback(); // <-- 換記錄時先停止播放
                    LoadSelectedRecord();
                }
            }
        }

        public string AudioFilePath
        {
            get => _audioFilePath;
            set => SetProperty(ref _audioFilePath, value);
        }

        public event PropertyChangedEventHandler? PropertyChanged;

        protected virtual void OnPropertyChanged([CallerMemberName] string? propertyName = null)
        {
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
        }

        public void NotifyPropertyChanged(string propertyName)
        {
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
        }

        protected bool SetProperty<T>(ref T backingStore, T value, [CallerMemberName] string? propertyName = null)
        {
            if (Equals(backingStore, value))
                return false;

            backingStore = value;
            OnPropertyChanged(propertyName);
            return true;
        }
        public Task StartNewRecordingAsync()
        {
            IsProcessing = false;
            IsPlaying = false;

            IsRecording = true;
            RecordingStatus = "錄音中...";
            _recordingStartTime = DateTime.Now;
            RecordingTime = "00:00:00";

            // 建立錄音檔案路徑
            var fileName = $"recording_{DateTime.Now:yyyyMMdd_HHmmss}.wav";
            var filePath = Path.Combine(_recordingsDirectory, fileName);
            AudioFilePath = filePath;

            // 初始化 NAudio 錄音
            _waveIn = new WaveInEvent
            {
                DeviceNumber = SelectedDeviceIndex, // ← 使用選擇的裝置
                WaveFormat = new WaveFormat(44100, 1) // 單聲道, 44.1kHz
            };
            _writer = new WaveFileWriter(filePath, _waveIn.WaveFormat);
            _waveIn.DataAvailable += (s, a) =>
            {
                _writer.Write(a.Buffer, 0, a.BytesRecorded);
                _writer.Flush();

                // 更新 AudioLevel 需要回到 UI 執行緒
                var level = a.Buffer.Take(a.BytesRecorded).Max(b => (double)b);
                _dispatcherQueue.TryEnqueue(() =>
                {
                    AudioLevel = level;
                });


            };
            _waveIn.StartRecording();

            return Task.CompletedTask;
        }

        public async Task PlayPauseAsync()
        {
            if (SelectedRecord == null)
                return;

            try
            {
                string filePath = SelectedRecord.FilePath;

                //  檔案不存在時，嘗試下載
                if (!File.Exists(filePath))
                {
                    var fileName = Path.GetFileName(filePath);

                    //  假設 folder 名稱就是檔名去掉副檔名，例如 meeting.wav -> meeting
                    var folder = Path.GetFileNameWithoutExtension(fileName);
                    var downloadUrl = $"{ApiBaseUrl}/uploads/{folder}/{fileName}";
                    var targetPath = Path.Combine(_recordingsDirectory, fileName);

                    Debug.WriteLine($"檔案不存在，嘗試下載: {downloadUrl}");

                    var audioBytes = await _httpClient.GetByteArrayAsync(downloadUrl);
                    await File.WriteAllBytesAsync(targetPath, audioBytes);

                    filePath = targetPath;
                    SelectedRecord.FilePath = targetPath;
                }

                if (!IsPlaying)
                {
                    //  初始化播放器
                    if (_audioFileReader == null || _waveOut == null)
                    {
                        _audioFileReader ??= new AudioFileReader(filePath);
                        _waveOut ??= new WaveOutEvent { DeviceNumber = SelectedOutputDeviceIndex };
                        _waveOut.Init(_audioFileReader);

                        _waveOut.PlaybackStopped += OnPlaybackStopped;

                        TotalDuration = _audioFileReader.TotalTime.TotalSeconds;
                        TotalTime = _audioFileReader.TotalTime.ToString(@"hh\:mm\:ss");



                        //  如果使用者在播放前有拖曳，這裡補上
                        if (_pendingSeekPosition.HasValue)
                        {
                            Debug.WriteLine($"[PlayPauseAsync] 應用延遲跳段到 {_pendingSeekPosition.Value}s");
                            SeekTo(_pendingSeekPosition.Value);
                            _pendingSeekPosition = null;
                        }
                    }

                    //  防呆：如果初始化失敗就跳出
                    if (_audioFileReader == null || _waveOut == null)
                    {
                        Debug.WriteLine("[PlayPauseAsync] 播放器初始化失敗");
                        RecordingStatus = "播放初始化失敗";
                        return;
                    }

                    _waveOut.Play();
                    IsPlaying = true;

                    //  背景更新播放進度
                    _ = Task.Run(async () =>
                    {
                        while (IsPlaying && _audioFileReader != null && _waveOut?.PlaybackState == PlaybackState.Playing)
                        {
                            await Task.Delay(200);
                            PlaybackPosition = _audioFileReader.CurrentTime.TotalSeconds;
                            _dispatcherQueue.TryEnqueue(UpdateTimeDisplay);
                        }
                    });
                }
                else
                {
                    //  暫停播放
                    _waveOut?.Pause();
                    IsPlaying = false;
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"播放音訊失敗: {ex.Message}");
                RecordingStatus = "播放失敗";
            }
        }



        public void StopPlayback()
        {
            try
            {
                IsPlaying = false;
                _waveOut?.Stop();
                ResetPlaybackState();
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"停止播放失敗: {ex.Message}");
            }
        }



        public void SeekTo(double positionInSeconds)
        {
            Debug.WriteLine($"[SeekTo] Seeking to {positionInSeconds}s");

            //  若播放器尚未初始化，記住位置並延後處理
            if (_audioFileReader == null || _waveOut == null)
            {
                Debug.WriteLine("[SeekTo] 尚未初始化播放器，延遲跳段");
                _pendingSeekPosition = positionInSeconds;
                return;
            }

            try
            {
                var wasPlaying = _waveOut.PlaybackState == PlaybackState.Playing;

                if (wasPlaying)
                    _waveOut.Pause(); //  暫停後跳段較穩定

                _audioFileReader.CurrentTime = TimeSpan.FromSeconds(positionInSeconds);
                PlaybackPosition = positionInSeconds;
                UpdateTimeDisplay();

                if (wasPlaying)
                    _waveOut.Play(); //  恢復播放
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[SeekTo] 錯誤: {ex.Message}");
                RecordingStatus = "跳段失敗";
            }
        }





        public void JumpToTimestamp(TimeSpan timestamp)
        {
            PlaybackPosition = timestamp.TotalSeconds;
            UpdateTimeDisplay();
        }

        private void UpdateTimeDisplay()
        {
            CurrentTime = TimeSpan.FromSeconds(PlaybackPosition).ToString(@"hh\:mm\:ss");
        }

        private async void LoadSelectedRecord()
        {
            if (SelectedRecord == null)
            {
                CurrentTranscriptSegments.Clear();
                Summary = string.Empty;
                TotalDuration = 0;
                TotalTime = "00:00:00";
                return;
            }

            try
            {
                // 讀取摘要
                if (!string.IsNullOrEmpty(SelectedRecord.SummaryUrl))
                {
                    Summary = await _httpClient.GetStringAsync($"{ApiBaseUrl}{SelectedRecord.SummaryUrl}");
                }

                // 讀取轉錄全文（不切段）
                if (!string.IsNullOrEmpty(SelectedRecord.TranscriptUrl))
                {
                    var transcriptUrl = $"{ApiBaseUrl}{SelectedRecord.TranscriptUrl}";
                    Debug.WriteLine($"嘗試下載 transcript.txt: {transcriptUrl}");

                    try
                    {
                        var transcriptText = await _httpClient.GetStringAsync(transcriptUrl);
                        Debug.WriteLine("取得 transcript.txt 成功，內容如下：");
                        Debug.WriteLine(transcriptText);

                        //  不再解析段落 → 直接顯示全文
                        CurrentTranscriptSegments.Clear();
                        CurrentTranscriptSegments.Add(new TranscriptSegment
                        {
                            TimeStamp = TimeSpan.Zero,
                            Speaker = "",  // 可省略
                            Text = transcriptText
                        });
                    }
                    catch (Exception ex)
                    {
                        Debug.WriteLine($"下載或顯示 transcript.txt 失敗: {ex.Message}");
                    }
                }
                else
                {
                    Debug.WriteLine("SelectedRecord.TranscriptUrl 為空！");
                }

            }
            catch (Exception ex)
            {
                Debug.WriteLine($"讀取轉錄與摘要錯誤: {ex.Message}");
                Summary = "(讀取失敗)";
                CurrentTranscriptSegments.Clear();
            }

            TotalDuration = SelectedRecord.Duration.TotalSeconds;
            TotalTime = SelectedRecord.Duration.ToString(@"hh\:mm\:ss");
            PlaybackPosition = 0;
            CurrentTime = "00:00:00";
            IsPlaying = false;
        }





        public void ResetToNewRecordingState()
        {
            StopPlayback(); // <-- 先停止播放
            SelectedRecord = null;
            IsRecording = false;
            IsPlaying = false;
            IsProcessing = false;
            RecordingTime = "00:00:00";
            RecordingStatus = "準備就緒";
            AudioLevel = 0;
            CurrentTime = "00:00:00";
            TotalTime = "00:00:00";
            PlaybackPosition = 0;
            TotalDuration = 0;

            CurrentTranscriptSegments.Clear();
            Summary = string.Empty;
        }

        public void UpdateRecordingTime()
        {
            if (IsRecording)
            {
                var elapsed = DateTime.Now - _recordingStartTime;
                RecordingTime = elapsed.ToString(@"hh\:mm\:ss");
            }
        }



    }




    // 轉錄結果的資料類別
    public class TranscriptionResult
    {
        public List<TranscriptSegment> Segments { get; set; } = new();
        public string Summary { get; set; } = string.Empty;
        public string? SummaryUrl { get; set; }
        public string? TranscriptUrl { get; set; }
    }




    public class ConferenceRecord
    {
        public Guid Id { get; set; }
        public string Title { get; set; } = string.Empty;
        public DateTime Date { get; set; }
        public TimeSpan Duration { get; set; }
        public string FilePath { get; set; } = string.Empty;
        public string Summary { get; set; } = string.Empty;
        public bool IsTranscribed { get; set; } = false;

        public string? SummaryUrl { get; set; }
        public string? TranscriptUrl { get; set; }

        public ObservableCollection<TranscriptSegment> TranscriptSegments { get; set; } = new();

        public string DisplayDate => Date.ToString("yyyy/MM/dd HH:mm");
        public string DisplayDuration => Duration.ToString(@"mm\:ss");
    }

    public class TranscriptSegment
    {
        public TimeSpan TimeStamp { get; set; }
        public string Text { get; set; } = string.Empty;
        public string Speaker { get; set; } = string.Empty;
        public int Timestamp
        {
            get => (int)TimeStamp.TotalSeconds;
            set => TimeStamp = TimeSpan.FromSeconds(value);
        }
        public string DisplayTimestamp => TimeStamp.ToString(@"hh\:mm\:ss");
    }
    public class TranscriptionApiResponse
    {
        public string Filename { get; set; }
        public string Status { get; set; }
        public Paths Paths { get; set; } = new();
        public string Transcript { get; set; } = string.Empty;
        public string Summary { get; set; } = string.Empty;
    }

    public class Paths
    {
        public string Audio_Url { get; set; } = string.Empty;
        public string Transcript_Url { get; set; } = string.Empty;
        public string Summary_Url { get; set; } = string.Empty;
    }


}