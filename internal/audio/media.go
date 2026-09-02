package audio

import (
	"encoding/binary"
	"errors"
	"image"
	"image/color"
	"io"
	"math"
	"os"
	"path/filepath"
	"strings"
)

func ResolvePlayablePath(rawPath string) (string, error) {
	if filepath.IsAbs(rawPath) {
		return "", errors.New("absolute paths are not allowed")
	}
	clean := filepath.Clean(rawPath)
	if clean == "." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) || clean == ".." {
		return "", errors.New("path must stay inside the repository")
	}
	ext := strings.ToLower(filepath.Ext(clean))
	switch ext {
	case ".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac":
	default:
		return "", errors.New("unsupported audio extension")
	}
	if clean != "data" && !strings.HasPrefix(clean, "data"+string(filepath.Separator)) {
		return "", errors.New("playback is restricted to files under data/")
	}
	wd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	return filepath.Join(wd, clean), nil
}

func ReadWAVMonoFloat64(path string) ([]float64, int, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, 0, err
	}
	defer f.Close()
	header := make([]byte, 12)
	if _, err := io.ReadFull(f, header); err != nil {
		return nil, 0, err
	}
	if string(header[0:4]) != "RIFF" || string(header[8:12]) != "WAVE" {
		return nil, 0, errors.New("not a RIFF/WAVE file")
	}
	var audioFormat, channels, bitsPerSample uint16
	var sampleRate uint32
	var data []byte
	for {
		chunkHeader := make([]byte, 8)
		if _, err := io.ReadFull(f, chunkHeader); err != nil {
			if errors.Is(err, io.EOF) || errors.Is(err, io.ErrUnexpectedEOF) {
				break
			}
			return nil, 0, err
		}
		chunkID := string(chunkHeader[0:4])
		chunkSize := binary.LittleEndian.Uint32(chunkHeader[4:8])
		chunk := make([]byte, chunkSize)
		if _, err := io.ReadFull(f, chunk); err != nil {
			return nil, 0, err
		}
		if chunkSize%2 == 1 {
			if _, err := f.Seek(1, io.SeekCurrent); err != nil {
				return nil, 0, err
			}
		}
		switch chunkID {
		case "fmt ":
			if len(chunk) < 16 {
				return nil, 0, errors.New("invalid fmt chunk")
			}
			audioFormat = binary.LittleEndian.Uint16(chunk[0:2])
			channels = binary.LittleEndian.Uint16(chunk[2:4])
			sampleRate = binary.LittleEndian.Uint32(chunk[4:8])
			bitsPerSample = binary.LittleEndian.Uint16(chunk[14:16])
		case "data":
			data = chunk
		}
	}
	if sampleRate == 0 || channels == 0 || len(data) == 0 {
		return nil, 0, errors.New("missing wav fmt or data")
	}
	if audioFormat != 1 && audioFormat != 3 {
		return nil, 0, errors.New("unsupported wav encoding")
	}
	bytesPerSample := int(bitsPerSample / 8)
	if bytesPerSample <= 0 {
		return nil, 0, errors.New("invalid bits per sample")
	}
	frameSize := int(channels) * bytesPerSample
	frames := len(data) / frameSize
	out := make([]float64, frames)
	for frame := 0; frame < frames; frame++ {
		sum := 0.0
		for ch := 0; ch < int(channels); ch++ {
			offset := frame*frameSize + ch*bytesPerSample
			sum += decodeWAVSample(data[offset:], audioFormat, bitsPerSample)
		}
		out[frame] = sum / float64(channels)
	}
	return out, int(sampleRate), nil
}

func RenderMelSpectrogramPNG(samples []float64, sampleRate, width, height, bands int) *image.RGBA {
	img := image.NewRGBA(image.Rect(0, 0, width, height))
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			img.SetRGBA(x, y, color.RGBA{R: 15, G: 23, B: 42, A: 255})
		}
	}
	if len(samples) == 0 || sampleRate <= 0 {
		return img
	}
	frameSize := minInt(2048, pow2Floor(maxInt(256, int(float64(sampleRate)*0.046))))
	hopSize := maxInt(128, frameSize/2)
	rawFrames := maxInt(1, (len(samples)-frameSize)/hopSize+1)
	frameStride := maxInt(1, int(math.Ceil(float64(rawFrames)/float64(width))))
	cols := int(math.Ceil(float64(rawFrames) / float64(frameStride)))
	frequencies := melFrequencies(sampleRate, bands)
	matrix := make([][]float64, bands)
	minVal := math.Inf(1)
	maxVal := math.Inf(-1)
	for b := range matrix {
		matrix[b] = make([]float64, cols)
	}
	for col := 0; col < cols; col++ {
		start := minInt(maxInt(0, len(samples)-frameSize), col*frameStride*hopSize)
		for band, freq := range frequencies {
			value := 10 * math.Log10(goertzelPower(samples, start, frameSize, freq, sampleRate))
			row := bands - band - 1
			matrix[row][col] = value
			minVal = math.Min(minVal, value)
			maxVal = math.Max(maxVal, value)
		}
	}
	valueRange := math.Max(1e-6, maxVal-minVal)
	for y := 0; y < height; y++ {
		row := minInt(bands-1, y*bands/height)
		for x := 0; x < width; x++ {
			col := minInt(cols-1, x*cols/width)
			t := (matrix[row][col] - minVal) / valueRange
			img.SetRGBA(x, y, spectrogramColor(t))
		}
	}
	return img
}

func decodeWAVSample(b []byte, audioFormat uint16, bitsPerSample uint16) float64 {
	if audioFormat == 3 && bitsPerSample == 32 && len(b) >= 4 {
		return float64(math.Float32frombits(binary.LittleEndian.Uint32(b[:4])))
	}
	switch bitsPerSample {
	case 8:
		return (float64(b[0]) - 128) / 128
	case 16:
		return float64(int16(binary.LittleEndian.Uint16(b[:2]))) / 32768
	case 24:
		v := int32(b[0]) | int32(b[1])<<8 | int32(b[2])<<16
		if v&0x800000 != 0 {
			v |= ^0xffffff
		}
		return float64(v) / 8388608
	case 32:
		return float64(int32(binary.LittleEndian.Uint32(b[:4]))) / 2147483648
	default:
		return 0
	}
}

func goertzelPower(samples []float64, start, frameSize int, frequency float64, sampleRate int) float64 {
	omega := 2 * math.Pi * frequency / float64(sampleRate)
	coeff := 2 * math.Cos(omega)
	q0, q1, q2 := 0.0, 0.0, 0.0
	for i := 0; i < frameSize; i++ {
		sample := 0.0
		if start+i >= 0 && start+i < len(samples) {
			windowValue := 0.5 - 0.5*math.Cos(2*math.Pi*float64(i)/float64(maxInt(1, frameSize-1)))
			sample = samples[start+i] * windowValue
		}
		q0 = coeff*q1 - q2 + sample
		q2 = q1
		q1 = q0
	}
	return math.Max(1e-12, q1*q1+q2*q2-coeff*q1*q2)
}

func melFrequencies(sampleRate, bands int) []float64 {
	minMel := hzToMel(30)
	maxMel := hzToMel(math.Min(float64(sampleRate)/2, 8000))
	out := make([]float64, bands)
	for i := 0; i < bands; i++ {
		t := 0.0
		if bands > 1 {
			t = float64(i) / float64(bands-1)
		}
		out[i] = melToHz(minMel + t*(maxMel-minMel))
	}
	return out
}

func hzToMel(hz float64) float64 {
	return 2595 * math.Log10(1+hz/700)
}

func melToHz(mel float64) float64 {
	return 700 * (math.Pow(10, mel/2595) - 1)
}

func spectrogramColor(t float64) color.RGBA {
	stops := [][3]uint8{
		{15, 23, 42},
		{30, 64, 175},
		{6, 182, 212},
		{163, 230, 53},
		{250, 204, 21},
	}
	scaled := math.Max(0, math.Min(1, t)) * float64(len(stops)-1)
	idx := minInt(len(stops)-2, int(math.Floor(scaled)))
	local := scaled - float64(idx)
	return color.RGBA{
		R: uint8(float64(stops[idx][0]) + (float64(stops[idx+1][0])-float64(stops[idx][0]))*local),
		G: uint8(float64(stops[idx][1]) + (float64(stops[idx+1][1])-float64(stops[idx][1]))*local),
		B: uint8(float64(stops[idx][2]) + (float64(stops[idx+1][2])-float64(stops[idx][2]))*local),
		A: 255,
	}
}

func pow2Floor(n int) int {
	if n <= 1 {
		return 1
	}
	out := 1
	for out*2 <= n {
		out *= 2
	}
	return out
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}
