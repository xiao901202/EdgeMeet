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
        private string _recordingStatus = "�ǳƴN��";
        private bool _isProcessing;
        private string _audioFilePath = string.Empty;
        private ConferenceRecord? _selectedRecord;
        private double _playbackPosition;
        private double _totalDuration;
        private string _currentTime = "00:00:00";
        private string _totalTime = "00:00:00";
        private string _recordingTime = "00:00:00";
        private DateTime _recordingStartTime;

        //��J
        private WaveInEvent? _waveIn;
        private WaveFileWriter? _writer;
        private readonly DispatcherQueue _dispatcherQueue = DispatcherQueue.GetForCurrentThread();

        // ���T����
        private AudioFileReader? _audioFileReader;
        private WaveOutEvent? _waveOut;

        private double? _pendingSeekPosition = null;  // �w���O����q��m�]�|����l�Ƽ��񾹮ɡ^

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
            Timeout = TimeSpan.FromMinutes(5) // �]�w�������W�ɮɶ�
        };
        private const string ApiBaseUrl = "http://localhost:8000";
        private const string TranscribeEndpoint = "/transcribe";
        private const string RecordEndpoint = "/record";
        private const string GetRecordsEndpoint = "/records";
        // �x�s�����ɮת��ؿ�
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
                    var buffer = new float[reader.WaveFormat.SampleRate]; // 1 �� 44100 samples
                    int index = 0;

                    while (true)
                    {
                        int samplesRead = reader.Read(buffer, 0, buffer.Length);
                        if (samplesRead == 0) break;

                        // ���˶��j�A���Y��ƶq�]�Ҧp�C 500 �� samples ���@�Ӯp�ȡ^
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

                    // �^�� UI �������s
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
                    Debug.WriteLine($"Ū���i�Υ���: {ex.Message}");
                }
            });
        }

        public MainViewModel()
        {


            ConferenceRecords = new ObservableCollection<ConferenceRecord>();
            CurrentTranscriptSegments = new ObservableCollection<TranscriptSegment>();

            // �إ߿����ɮץؿ�
            _recordingsDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "ConferenceAssistant", "Recordings");
            Directory.CreateDirectory(_recordingsDirectory);


            //  ���y���T��J�˸m�]���J���^
            for (int i = 0; i < WaveIn.DeviceCount; i++)
            {
                var deviceInfo = WaveIn.GetCapabilities(i);
                InputDevices.Add(deviceInfo.ProductName);
            }
            // ���T��X�]�ơ]��z�B�վ��^
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



        // �W�ǭ��ɨ� FastAPI �è��o������G
        public async Task<TranscriptionResult?> UploadAndTranscribeAsync(string filePath)
        {
            if (!File.Exists(filePath))
            {
                Debug.WriteLine($"�ɮפ��s�b: {filePath}");
                return null;
            }

            try
            {
                using var form = new MultipartFormDataContent();
                using var fileStream = File.OpenRead(filePath);
                using var fileContent = new StreamContent(fileStream);

                // �]�w���T�� Content-Type
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

                Debug.WriteLine($"�}�l�W���ɮ�: {Path.GetFileName(filePath)}");

                var response = await _httpClient.PostAsync($"{ApiBaseUrl}{TranscribeEndpoint}", form);

                if (response.IsSuccessStatusCode)
                {
                    var jsonResponse = await response.Content.ReadAsStringAsync();
                    Debug.WriteLine($"����^��: {jsonResponse}");

                    // �ѪR JSON �^��
                    var options = new JsonSerializerOptions
                    {
                        PropertyNameCaseInsensitive = true
                    };

                    var apiResponse = JsonSerializer.Deserialize<TranscriptionApiResponse>(jsonResponse, options);

                    if (apiResponse == null)
                    {
                        Debug.WriteLine("API �^�ǸѪR����");
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
                    Debug.WriteLine($"�W�ǥ���: {response.StatusCode} - {error}");
                    RecordingStatus = $"�������: {response.StatusCode}";
                }
            }
            catch (TaskCanceledException)
            {
                Debug.WriteLine("�ШD�W��");
                RecordingStatus = "����W�ɡA�еy��A��";
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"�W�Ǯɵo�Ϳ��~: {ex.Message}");
                RecordingStatus = $"���~: {ex.Message}";
            }

            return null;
        }

        // �N���㪺�|ĳ�O���W�Ǩ���
        public async Task UploadConferenceRecordAsync(ConferenceRecord record)
        {
            try
            {
                var recordData = new
                {
                    id = record.Id.ToString(),
                    title = record.Title,
                    date = record.Date.ToString("O"), // ISO 8601 �榡
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
                    Debug.WriteLine("�|ĳ�O���W�Ǧ��\");
                }
                else
                {
                    var error = await response.Content.ReadAsStringAsync();
                    Debug.WriteLine($"�|ĳ�O���W�ǥ���: {error}");
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"�W�Ƿ|ĳ�O���ɵo�Ϳ��~: {ex.Message}");
            }
        }
        //private const string GetRecordsEndpoint = "/records"; // �s�W�o��
        // ���o�|ĳ�O���C��
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
                    Debug.WriteLine($"���o�O������: {response.StatusCode}");
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"���J�O���o�Ϳ��~: {ex.Message}");
            }
        }

        //�M�μ��񵲧��ƥ󪺳B�z��k
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

        // ��������æ۰ʳB�z
        public async Task StopRecordingAsync()
        {
            IsRecording = false;
            RecordingStatus = "�x�s����...";
            IsProcessing = true;

            var recordingDuration = DateTime.Now - _recordingStartTime;
            // �������
            _waveIn?.StopRecording();
            _waveIn?.Dispose();
            _waveIn = null;

            _writer?.Dispose();
            _writer = null;

            // �Ыطs���|ĳ�O��
            var newRecord = new ConferenceRecord
            {
                Id = Guid.NewGuid(),
                Title = $"�|ĳ�O�� {DateTime.Now:MM/dd HH:mm}",
                Date = DateTime.Now,
                Duration = recordingDuration,
                FilePath = AudioFilePath,
                IsTranscribed = false
            };

            ConferenceRecords.Insert(0, newRecord);
            SelectedRecord = newRecord;

            IsProcessing = false;
            RecordingStatus = "��������";
            RecordingTime = "00:00:00";
        }

        // �}�l����]�i�H�q UI ���Ĳ�o�Φ۰�Ĳ�o�^
        public async Task StartTranscriptionAsync()
        {
            if (SelectedRecord == null || string.IsNullOrEmpty(SelectedRecord.FilePath)) return;

            IsProcessing = true;
            RecordingStatus = "���b�i��AI�y�����...";

            try
            {
                // �W�ǭ��ɨè��o������G
                var result = await UploadAndTranscribeAsync(SelectedRecord.FilePath);

                if (result != null)
                {
                    //  �N��ݦ^�Ǫ� .txt �ɮ׺��}�g�J SelectedRecord
                    SelectedRecord.SummaryUrl = result.SummaryUrl;
                    SelectedRecord.TranscriptUrl = result.TranscriptUrl;

                    // �M���ª�������e
                    SelectedRecord.TranscriptSegments.Clear();
                    CurrentTranscriptSegments.Clear();

                    // �[�J�s������q��
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

                    // �]�w�K�n
                    SelectedRecord.Summary = result.Summary;
                    Summary = result.Summary;

                    // �аO���w���
                    SelectedRecord.IsTranscribed = true;

                    // �W�ǧ��㪺�|ĳ�O������
                    await UploadConferenceRecordAsync(SelectedRecord);

                    RecordingStatus = "�������";
                }
                else
                {
                    RecordingStatus = "�������";
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"����L�{���o�Ϳ��~: {ex.Message}");
                RecordingStatus = $"������~: {ex.Message}";
            }
            finally
            {
                IsProcessing = false;
            }
        }


        // �W�ǥ~������
        public async Task UploadAudioFileAsync(string filePath)
        {
            AudioFilePath = filePath;
            IsProcessing = true;
            RecordingStatus = "�B�z�W�Ǫ����T...";

            try
            {
                // �ƻs�ɮר����ε{���ؿ�
                var fileName = Path.GetFileName(filePath);
                var targetPath = Path.Combine(_recordingsDirectory, fileName);

                if (filePath != targetPath)
                {
                    File.Copy(filePath, targetPath, true);
                }

                // �إ߷s�O��
                var newRecord = new ConferenceRecord
                {
                    Id = Guid.NewGuid(),
                    Title = $"�W��: {Path.GetFileNameWithoutExtension(fileName)}",
                    Date = DateTime.Now,
                    Duration = await GetAudioDuration(targetPath), // �ݭn��@���o���ɪ��ת���k
                    FilePath = targetPath,
                    IsTranscribed = false
                };

                ConferenceRecords.Insert(0, newRecord);
                SelectedRecord = newRecord;

                // �۰ʶ}�l���
                await StartTranscriptionAsync();
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"�B�z�W���ɮ׮ɵo�Ϳ��~: {ex.Message}");
                RecordingStatus = $"�W�ǿ��~: {ex.Message}";
            }
            finally
            {
                IsProcessing = false;
            }
        }

        // ���o���ɪ��ס]�ݭn��@�^
        private async Task<TimeSpan> GetAudioDuration(string filePath)
        {
            // �o�����Өϥέ��T�B�z�w�Ө��o��ڪ���
            // �Ȯɪ�^�w�]��
            await Task.CompletedTask;
            return TimeSpan.FromMinutes(10);
        }


        // �ݩʩM��L��k�O�����...
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
                    StopPlayback(); // <-- ���O���ɥ������
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
            RecordingStatus = "������...";
            _recordingStartTime = DateTime.Now;
            RecordingTime = "00:00:00";

            // �إ߿����ɮ׸��|
            var fileName = $"recording_{DateTime.Now:yyyyMMdd_HHmmss}.wav";
            var filePath = Path.Combine(_recordingsDirectory, fileName);
            AudioFilePath = filePath;

            // ��l�� NAudio ����
            _waveIn = new WaveInEvent
            {
                DeviceNumber = SelectedDeviceIndex, // �� �ϥο�ܪ��˸m
                WaveFormat = new WaveFormat(44100, 1) // ���n�D, 44.1kHz
            };
            _writer = new WaveFileWriter(filePath, _waveIn.WaveFormat);
            _waveIn.DataAvailable += (s, a) =>
            {
                _writer.Write(a.Buffer, 0, a.BytesRecorded);
                _writer.Flush();

                // ��s AudioLevel �ݭn�^�� UI �����
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

                //  �ɮפ��s�b�ɡA���դU��
                if (!File.Exists(filePath))
                {
                    var fileName = Path.GetFileName(filePath);

                    //  ���] folder �W�ٴN�O�ɦW�h�����ɦW�A�Ҧp meeting.wav -> meeting
                    var folder = Path.GetFileNameWithoutExtension(fileName);
                    var downloadUrl = $"{ApiBaseUrl}/uploads/{folder}/{fileName}";
                    var targetPath = Path.Combine(_recordingsDirectory, fileName);

                    Debug.WriteLine($"�ɮפ��s�b�A���դU��: {downloadUrl}");

                    var audioBytes = await _httpClient.GetByteArrayAsync(downloadUrl);
                    await File.WriteAllBytesAsync(targetPath, audioBytes);

                    filePath = targetPath;
                    SelectedRecord.FilePath = targetPath;
                }

                if (!IsPlaying)
                {
                    //  ��l�Ƽ���
                    if (_audioFileReader == null || _waveOut == null)
                    {
                        _audioFileReader ??= new AudioFileReader(filePath);
                        _waveOut ??= new WaveOutEvent { DeviceNumber = SelectedOutputDeviceIndex };
                        _waveOut.Init(_audioFileReader);

                        _waveOut.PlaybackStopped += OnPlaybackStopped;

                        TotalDuration = _audioFileReader.TotalTime.TotalSeconds;
                        TotalTime = _audioFileReader.TotalTime.ToString(@"hh\:mm\:ss");



                        //  �p�G�ϥΪ̦b����e���즲�A�o�̸ɤW
                        if (_pendingSeekPosition.HasValue)
                        {
                            Debug.WriteLine($"[PlayPauseAsync] ���Ω�����q�� {_pendingSeekPosition.Value}s");
                            SeekTo(_pendingSeekPosition.Value);
                            _pendingSeekPosition = null;
                        }
                    }

                    //  ���b�G�p�G��l�ƥ��ѴN���X
                    if (_audioFileReader == null || _waveOut == null)
                    {
                        Debug.WriteLine("[PlayPauseAsync] ���񾹪�l�ƥ���");
                        RecordingStatus = "�����l�ƥ���";
                        return;
                    }

                    _waveOut.Play();
                    IsPlaying = true;

                    //  �I����s����i��
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
                    //  �Ȱ�����
                    _waveOut?.Pause();
                    IsPlaying = false;
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"���񭵰T����: {ex.Message}");
                RecordingStatus = "���񥢱�";
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
                Debug.WriteLine($"����񥢱�: {ex.Message}");
            }
        }



        public void SeekTo(double positionInSeconds)
        {
            Debug.WriteLine($"[SeekTo] Seeking to {positionInSeconds}s");

            //  �Y���񾹩|����l�ơA�O���m�é���B�z
            if (_audioFileReader == null || _waveOut == null)
            {
                Debug.WriteLine("[SeekTo] �|����l�Ƽ��񾹡A������q");
                _pendingSeekPosition = positionInSeconds;
                return;
            }

            try
            {
                var wasPlaying = _waveOut.PlaybackState == PlaybackState.Playing;

                if (wasPlaying)
                    _waveOut.Pause(); //  �Ȱ�����q��í�w

                _audioFileReader.CurrentTime = TimeSpan.FromSeconds(positionInSeconds);
                PlaybackPosition = positionInSeconds;
                UpdateTimeDisplay();

                if (wasPlaying)
                    _waveOut.Play(); //  ��_����
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[SeekTo] ���~: {ex.Message}");
                RecordingStatus = "���q����";
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
                // Ū���K�n
                if (!string.IsNullOrEmpty(SelectedRecord.SummaryUrl))
                {
                    Summary = await _httpClient.GetStringAsync($"{ApiBaseUrl}{SelectedRecord.SummaryUrl}");
                }

                // Ū���������]�����q�^
                if (!string.IsNullOrEmpty(SelectedRecord.TranscriptUrl))
                {
                    var transcriptUrl = $"{ApiBaseUrl}{SelectedRecord.TranscriptUrl}";
                    Debug.WriteLine($"���դU�� transcript.txt: {transcriptUrl}");

                    try
                    {
                        var transcriptText = await _httpClient.GetStringAsync(transcriptUrl);
                        Debug.WriteLine("���o transcript.txt ���\�A���e�p�U�G");
                        Debug.WriteLine(transcriptText);

                        //  ���A�ѪR�q�� �� ������ܥ���
                        CurrentTranscriptSegments.Clear();
                        CurrentTranscriptSegments.Add(new TranscriptSegment
                        {
                            TimeStamp = TimeSpan.Zero,
                            Speaker = "",  // �i�ٲ�
                            Text = transcriptText
                        });
                    }
                    catch (Exception ex)
                    {
                        Debug.WriteLine($"�U������� transcript.txt ����: {ex.Message}");
                    }
                }
                else
                {
                    Debug.WriteLine("SelectedRecord.TranscriptUrl ���šI");
                }

            }
            catch (Exception ex)
            {
                Debug.WriteLine($"Ū������P�K�n���~: {ex.Message}");
                Summary = "(Ū������)";
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
            StopPlayback(); // <-- �������
            SelectedRecord = null;
            IsRecording = false;
            IsPlaying = false;
            IsProcessing = false;
            RecordingTime = "00:00:00";
            RecordingStatus = "�ǳƴN��";
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




    // ������G��������O
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