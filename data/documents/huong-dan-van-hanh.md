# Hướng dẫn vận hành dịch vụ

## Khởi động môi trường phát triển

Dịch vụ cần hai tiến trình chạy song song: kho vector và ứng dụng web. Kho vector được
khởi động trước bằng trình quản lý container, ứng dụng web khởi động sau và sẽ tự kết
nối tới cổng mặc định của kho vector.

Nếu kho vector chưa sẵn sàng vào lúc ứng dụng web khởi động, ứng dụng sẽ không phục vụ
được trang giao diện. Đây là hành vi đã biết chứ không phải lỗi: bộ khởi tạo dựng sẵn
đối tượng điều phối một lần duy nhất trong vòng đời ứng dụng.

## Nạp tài liệu lần đầu

Sau khi hai tiến trình đã chạy, chạy kịch bản nạp để đẩy toàn bộ tài liệu trong thư mục
tài liệu vào kho vector. Kịch bản này đọc từng tệp, cắt thành đoạn, sinh vector cho từng
đoạn, rồi ghi vào bộ sưu tập.

Chi phí thật phát sinh ở bước sinh vector vì nó gọi ra dịch vụ bên ngoài. Số tiền tỉ lệ
thuận với tổng số ký tự chứ không phải số tệp, nên một tệp PDF dài vài trăm trang tốn
hơn nhiều so với hai mươi tệp văn bản ngắn.

## Theo dõi tình trạng

Điểm cuối kiểm tra tình trạng trả về ba thông tin: trạng thái tổng thể, kho vector có
kết nối được không, và dịch vụ mô hình có phản hồi không. Trạng thái tổng thể chỉ ở mức
tốt khi cả hai thành phần đều đạt.

Cần hiểu đúng giới hạn của điểm cuối này. Nó xác nhận kết nối mạng tới từng thành phần,
không xác nhận rằng một truy vấn đầy đủ sẽ chạy trót lọt. Một chứng thực hết hạn có thể
vẫn cho kết quả tốt ở bước kiểm tra tình trạng trong khi mọi truy vấn thật đều hỏng.

## Sao lưu và khôi phục

Dữ liệu vector nằm trong ổ đĩa gắn vào container kho vector. Sao lưu nghĩa là sao chép
ổ đĩa đó, không phải sao chép thư mục tài liệu. Hai thứ này khác nhau: thư mục tài liệu
là nguồn, ổ đĩa vector là kết quả đã xử lý.

Trong trường hợp mất hoàn toàn kho vector, đường khôi phục là dựng lại bộ sưu tập rồi
chạy lại kịch bản nạp từ thư mục tài liệu. Đường này chỉ hoạt động khi mọi nguồn đang
có trong chỉ mục đều còn tệp trên đĩa. Tài liệu được nạp qua đường liên kết mạng không
có bản sao cục bộ, nên chúng sẽ mất và phải nạp lại thủ công.

## Đổi cấu hình lúc chạy

Phần lớn tham số đọc từ biến môi trường và chỉ có hiệu lực khi tiến trình khởi động
lại. Riêng với container, sửa tệp môi trường rồi khởi động lại là chưa đủ: biến môi
trường được cố định vào lúc container được tạo, nên phải tạo lại container thì giá trị
mới mới được nạp.

Biến tuỳ chọn nên để ở dạng chú thích thay vì gán giá trị rỗng. Một giá trị rỗng khác
với việc không đặt biến, và trong vài trường hợp nó làm thư viện phía dưới phát cảnh
báo hoặc chọn nhánh xử lý sai.

## Cổng chất lượng trước khi triển khai

Bốn lệnh phải sạch trước khi coi một thay đổi là xong: kiểm tra lint, kiểm tra định
dạng, kiểm tra kiểu tĩnh, và chạy toàn bộ bộ kiểm thử. Bộ kiểm thử chạy hoàn toàn ngoại
tuyến, không gọi mạng, nên thời gian chạy tính bằng giây chứ không phải phút.
